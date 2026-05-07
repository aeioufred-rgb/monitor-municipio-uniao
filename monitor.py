#!/usr/bin/env python3
"""
Monitor diário de processos: Município x União
Teses tributárias e financeiras

Consulta a API Pública do DataJud (CNJ) nos endpoints TRF4, TRF5, STF e STJ,
filtra processos novos por (a) janela temporal, (b) localização geográfica
(IBGE) para PE/PB/RN/AL/RS, e (c) palavras-chave de assunto/classe.

Tenta validar as partes (autor=município, réu=União) a partir dos próprios
dados retornados pelo DataJud. Casos sem dados de partes são marcados como
"a verificar" e levam link direto para a consulta pública do tribunal.

Envia digest HTML por e-mail.
"""

import os
import re
import json
import time
import smtplib
import traceback
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

# Variáveis de ambiente (vêm dos secrets do GitHub Actions)
def env(name, required=True, default=None):
    v = os.environ.get(name, default)
    if required and not v:
        raise SystemExit(f"Variável de ambiente obrigatória não definida: {name}")
    return v


API_KEY = env("DATAJUD_API_KEY")
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
EMAIL_TO = env("EMAIL_TO")
SMTP_HOST = env("SMTP_HOST", required=False, default="smtp.gmail.com")
SMTP_PORT = int(env("SMTP_PORT", required=False, default="587"))

ENDPOINTS = {
    "TRF5": "https://api-publica.datajud.cnj.jus.br/api_publica_trf5/_search",
    "TRF4": "https://api-publica.datajud.cnj.jus.br/api_publica_trf4/_search",
    "STF":  "https://api-publica.datajud.cnj.jus.br/api_publica_stf/_search",
    "STJ":  "https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search",
}

HEADERS = {
    "Authorization": f"APIKey {API_KEY}",
    "Content-Type": "application/json",
}

# Faixas IBGE por estado de interesse
IBGE_RANGES_TRF5 = [
    (2400000, 2499999),  # RN
    (2500000, 2599999),  # PB
    (2600000, 2699999),  # PE
    (2700000, 2799999),  # AL
]
IBGE_RANGES_TRF4 = [
    (4300000, 4399999),  # RS
]
STATE_FROM_IBGE_PREFIX = {
    24: "RN", 25: "PB", 26: "PE", 27: "AL", 43: "RS",
}

# Janela de varredura: pega tudo dos últimos N dias e usa estado para deduplicar
WINDOW_DAYS = 14
DEDUPE_RETENTION_DAYS = 90

ROOT = Path(__file__).parent.resolve()
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "reported.json"


# =============================================================================
# CARREGAMENTO DE CONFIGS
# =============================================================================

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_configs():
    assuntos = load_json(ROOT / "assuntos.json")
    classes = load_json(ROOT / "classes.json")
    return assuntos, classes


def load_reported():
    if STATE_FILE.exists():
        try:
            data = load_json(STATE_FILE)
        except Exception:
            data = {}
    else:
        data = {}
    reported = data.get("reported", {})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DEDUPE_RETENTION_DAYS)).isoformat()
    reported = {k: v for k, v in reported.items() if v >= cutoff}
    return {"reported": reported}


def save_reported(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False, sort_keys=True)


# =============================================================================
# CONSTRUÇÃO DAS QUERIES
# =============================================================================

def build_query(tribunal, since_date_iso, ibge_ranges, assuntos_cfg):
    """Constrói o corpo da query Elasticsearch para um tribunal."""

    # Cláusula temática: códigos OU palavras-chave de assunto
    thematic_should = []
    for codigo in assuntos_cfg.get("codigos", []):
        thematic_should.append({"term": {"assuntos.codigo": codigo}})
    for kw in assuntos_cfg.get("palavras_chave", []):
        thematic_should.append({"match_phrase": {"assuntos.nome": kw}})

    filters = [
        {"range": {"dataAjuizamento": {"gte": since_date_iso}}},
        {"bool": {"should": thematic_should, "minimum_should_match": 1}},
    ]

    # Filtragem geográfica só para TRFs (STF/STJ são nacionais)
    if ibge_ranges:
        ibge_should = [
            {"range": {"orgaoJulgador.codigoMunicipioIBGE": {"gte": lo, "lte": hi}}}
            for lo, hi in ibge_ranges
        ]
        filters.append({"bool": {"should": ibge_should, "minimum_should_match": 1}})

    return {
        "size": 100,
        "sort": [{"@timestamp": {"order": "asc"}}, {"_id": {"order": "asc"}}],
        "query": {"bool": {"filter": filters}},
    }


def fetch_tribunal(tribunal, endpoint, query):
    """Consulta um tribunal com paginação search_after."""
    hits = []
    body = json.loads(json.dumps(query))  # cópia profunda
    page_count = 0
    max_pages = 50  # salvaguarda

    while page_count < max_pages:
        try:
            r = requests.post(endpoint, headers=HEADERS, json=body, timeout=60)
        except requests.RequestException as e:
            print(f"[{tribunal}] erro de rede: {e}")
            break

        if r.status_code != 200:
            print(f"[{tribunal}] HTTP {r.status_code}: {r.text[:300]}")
            break

        try:
            payload = r.json()
        except ValueError:
            print(f"[{tribunal}] resposta não-JSON: {r.text[:200]}")
            break

        page = payload.get("hits", {}).get("hits", [])
        if not page:
            break

        hits.extend(page)
        page_count += 1

        if len(page) < body["size"]:
            break

        last_sort = page[-1].get("sort")
        if not last_sort:
            break
        body["search_after"] = last_sort

        time.sleep(0.4)  # cortesia

    print(f"[{tribunal}] coletados {len(hits)} processos em {page_count} páginas")
    return hits


# =============================================================================
# CLASSIFICAÇÃO DE PARTES
# =============================================================================

MUNICIPIO_PATTERNS = [
    re.compile(r"\bMUNIC[IÍ]PIO\s+DE\s+", re.IGNORECASE),
    re.compile(r"\bMUNIC[IÍ]PIO\s+DO\s+", re.IGNORECASE),
    re.compile(r"\bPREFEITURA\s+(MUNICIPAL\s+)?DE\s+", re.IGNORECASE),
    re.compile(r"^MUNIC[IÍ]PIO\s+", re.IGNORECASE),
    re.compile(r"\bC[AÂ]MARA\s+MUNICIPAL\s+DE\s+", re.IGNORECASE),
]

UNIAO_PATTERNS = [
    re.compile(r"\bUNI[AÃ]O(\s+FEDERAL)?\b", re.IGNORECASE),
    re.compile(r"\bFAZENDA\s+NACIONAL\b", re.IGNORECASE),
    re.compile(r"\bADVOCACIA[- ]GERAL\s+DA\s+UNI[AÃ]O\b", re.IGNORECASE),
    re.compile(r"\bAGU\b"),
    re.compile(r"\bPGFN\b"),
    re.compile(r"\bFNDE\b"),
    re.compile(r"\bFUNDO\s+NACIONAL\b", re.IGNORECASE),
    re.compile(r"\bMINIST[EÉ]RIO\s+(DA|DO)\s+", re.IGNORECASE),
    re.compile(r"\bRECEITA\s+FEDERAL\b", re.IGNORECASE),
    re.compile(r"\bINSS\b"),
    re.compile(r"\bANP\b"),
    re.compile(r"\bANEEL\b"),
    re.compile(r"\bIBAMA\b"),
    re.compile(r"\bICMBIO\b"),
    re.compile(r"\bSUDENE\b"),
    re.compile(r"\bDNIT\b"),
    re.compile(r"\bDNOCS\b"),
    re.compile(r"\bSECRETARIA\s+DO\s+TESOURO\s+NACIONAL\b", re.IGNORECASE),
    re.compile(r"\bBANCO\s+DO\s+BRASIL\b", re.IGNORECASE),
    re.compile(r"\bCAIXA\s+ECON[OÔ]MICA\s+FEDERAL\b", re.IGNORECASE),
]


def is_municipio(nome):
    return any(p.search(nome or "") for p in MUNICIPIO_PATTERNS)


def is_uniao(nome):
    return any(p.search(nome or "") for p in UNIAO_PATTERNS)


def extract_partes(hit):
    """Extrai listas de autores e réus a partir do _source do hit."""
    src = hit.get("_source", {})
    partes_raw = src.get("partes") or src.get("polos") or []

    autores, reus = [], []
    for p in partes_raw:
        if not isinstance(p, dict):
            continue
        polo = (p.get("polo") or p.get("tipoPolo") or p.get("tipo") or "").upper().strip()

        nome = ""
        pessoa = p.get("pessoa")
        if isinstance(pessoa, dict):
            nome = pessoa.get("nome") or pessoa.get("razaoSocial") or ""
        if not nome:
            nome = p.get("nome") or p.get("razaoSocial") or ""

        if not nome:
            continue

        if polo in ("ATIVO", "AT", "AUTOR", "REQUERENTE", "EXEQUENTE", "EMBARGANTE", "RECORRENTE"):
            autores.append(nome)
        elif polo in ("PASSIVO", "PA", "REU", "RÉU", "REQUERIDO", "EXECUTADO", "EMBARGADO", "RECORRIDO"):
            reus.append(nome)

    return autores, reus


def validate_hit(hit):
    """
    Retorna (status, autores, reus) onde status é:
    - 'CONFIRMADO': autor é município E réu é União/órgão federal
    - 'PROVAVEL':   autor é município (réu pode estar ambíguo)
    - 'VERIFICAR':  DataJud não retornou partes; precisa olhar consulta pública
    - 'DESCARTAR':  partes presentes mas autor não é município
    """
    autores, reus = extract_partes(hit)

    if not autores and not reus:
        return "VERIFICAR", [], []

    autor_municipio = any(is_municipio(n) for n in autores)
    reu_uniao = any(is_uniao(n) for n in reus)

    if autor_municipio and reu_uniao:
        return "CONFIRMADO", autores, reus
    if autor_municipio:
        return "PROVAVEL", autores, reus
    return "DESCARTAR", autores, reus


# =============================================================================
# CLASSE / EXCLUSÕES
# =============================================================================

def get_classe_nome(hit):
    src = hit.get("_source", {})
    classe = src.get("classe", {})
    if isinstance(classe, dict):
        return classe.get("nome") or ""
    return ""


def passa_filtro_classe(hit, classes_cfg):
    """Aplica include/exclude por substring no nome da classe."""
    nome = get_classe_nome(hit).lower()
    if not nome:
        return True  # se não tem classe, deixa passar (raro)

    for ex in classes_cfg.get("excluir_palavras_chave", []):
        if ex.lower() in nome:
            return False

    incluir = classes_cfg.get("incluir_palavras_chave", [])
    if not incluir:
        return True
    for inc in incluir:
        if inc.lower() in nome:
            return True
    return False


# =============================================================================
# METADADOS DO HIT
# =============================================================================

def get_uf_from_hit(hit):
    src = hit.get("_source", {})
    oj = src.get("orgaoJulgador") or {}
    codigo = oj.get("codigoMunicipioIBGE")
    if codigo is not None:
        try:
            prefix = int(codigo) // 100000
            return STATE_FROM_IBGE_PREFIX.get(prefix, "?")
        except (ValueError, TypeError):
            pass
    return "?"


def get_assuntos_str(hit):
    src = hit.get("_source", {})
    assuntos = src.get("assuntos") or []
    nomes = []
    for a in assuntos:
        if isinstance(a, dict):
            n = a.get("nome")
            if n:
                nomes.append(n)
    return "; ".join(nomes[:3])  # primeiros 3


def get_data_ajuizamento(hit):
    src = hit.get("_source", {})
    return (src.get("dataAjuizamento") or "")[:10]


def get_orgao_julgador(hit):
    src = hit.get("_source", {})
    oj = src.get("orgaoJulgador") or {}
    return oj.get("nome", "")


def get_numero_processo(hit):
    src = hit.get("_source", {})
    return src.get("numeroProcesso", "")


def consulta_publica_url(numero, tribunal):
    if not numero:
        return ""
    only_digits = re.sub(r"\D", "", numero)

    if tribunal == "TRF5":
        return f"https://pje.trf5.jus.br/pje/ConsultaPublica/listView.seam?cidConsulta=&numeroProcesso={numero}"
    if tribunal == "TRF4":
        return f"https://eproc.trf4.jus.br/eproc2trf4/externo_controlador.php?acao=processo_consulta_publica&num_processo={only_digits}"
    if tribunal == "STF":
        return f"https://portal.stf.jus.br/processos/listarProcessos.asp?termo={numero}"
    if tribunal == "STJ":
        return f"https://processo.stj.jus.br/processo/pesquisa/?aplicacao=processos.ea&tipoPesquisa=tipoPesquisaGenerica&termo={numero}"
    return ""


# =============================================================================
# RENDERIZAÇÃO DO E-MAIL
# =============================================================================

CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color:#222; line-height:1.45; max-width:980px; margin:auto; padding:20px; }
h1 { font-size:20px; margin:0 0 4px 0; }
h2 { font-size:16px; margin:24px 0 8px 0; padding:8px 12px; border-radius:4px; }
.h-confirmado { background:#e8f5e9; color:#1b5e20; }
.h-provavel   { background:#fff8e1; color:#7c5e00; }
.h-verificar  { background:#eceff1; color:#37474f; }
.h-falhas     { background:#ffebee; color:#b71c1c; }
table { border-collapse:collapse; width:100%; font-size:13px; margin-bottom:16px; }
th, td { border:1px solid #ddd; padding:6px 8px; vertical-align:top; text-align:left; }
th { background:#fafafa; }
.small { color:#777; font-size:12px; }
.tag { display:inline-block; padding:1px 6px; border-radius:3px; background:#eef; color:#225; font-size:11px; }
.muted { color:#888; }
a { color:#1565c0; text-decoration:none; }
a:hover { text-decoration:underline; }
.summary { background:#f7f7f7; padding:10px 14px; border-radius:4px; margin:10px 0 18px; }
.summary span { margin-right:18px; }
.footer { color:#888; font-size:12px; margin-top:30px; border-top:1px solid #eee; padding-top:12px; }
"""


def fmt_partes(lst, max_len=120):
    if not lst:
        return '<span class="muted">—</span>'
    s = " / ".join(lst)
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def render_table(rows, mostrar_partes=True):
    if not rows:
        return '<p class="muted">Nenhum processo nesta categoria.</p>'

    head = "<tr><th>Nº CNJ</th><th>UF/Tribunal</th><th>Ajuizado</th><th>Classe</th><th>Assunto</th>"
    if mostrar_partes:
        head += "<th>Autor</th><th>Réu</th>"
    head += "<th>Consulta</th></tr>"

    body_rows = []
    for r in rows:
        link = r["link_consulta"]
        link_html = f'<a href="{link}" target="_blank">abrir</a>' if link else "—"
        cells = [
            f'<td>{r["numero"]}</td>',
            f'<td>{r["uf"]} / {r["tribunal"]}</td>',
            f'<td>{r["ajuizado"]}</td>',
            f'<td>{r["classe"]}</td>',
            f'<td>{r["assuntos"]}</td>',
        ]
        if mostrar_partes:
            cells.append(f'<td>{fmt_partes(r["autores"])}</td>')
            cells.append(f'<td>{fmt_partes(r["reus"])}</td>')
        cells.append(f'<td>{link_html}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return f"<table>{head}{''.join(body_rows)}</table>"


def render_email(buckets, stats, falhas):
    confirmados = buckets["CONFIRMADO"]
    provaveis = buckets["PROVAVEL"]
    verificar = buckets["VERIFICAR"]

    hoje = datetime.now().strftime("%d/%m/%Y")

    blocos = [
        f"<style>{CSS}</style>",
        f"<h1>Monitor Município x União — {hoje}</h1>",
        '<div class="small">Teses tributárias e financeiras — recorte: PE, PB, RN, AL, RS + STF/STJ</div>',
        '<div class="summary">',
        f'<span><b>{len(confirmados)}</b> confirmados</span>',
        f'<span><b>{len(provaveis)}</b> prováveis</span>',
        f'<span><b>{len(verificar)}</b> a verificar</span>',
        f'<span class="muted">{stats["total_candidatos"]} candidatos brutos</span>',
        '</div>',
    ]

    blocos.append('<h2 class="h-confirmado">🟢 Confirmados — autor é município, réu é União/órgão federal</h2>')
    blocos.append(render_table(confirmados))

    blocos.append('<h2 class="h-provavel">🟡 Prováveis — autor é município, réu não casou automaticamente</h2>')
    blocos.append(render_table(provaveis))

    blocos.append('<h2 class="h-verificar">⚪ A verificar — DataJud não retornou as partes</h2>')
    blocos.append(render_table(verificar, mostrar_partes=False))

    if falhas:
        blocos.append('<h2 class="h-falhas">⚠️ Falhas de coleta</h2>')
        blocos.append("<ul>")
        for f in falhas:
            blocos.append(f"<li>{f}</li>")
        blocos.append("</ul>")

    blocos.append(
        '<div class="footer">'
        f'Janela: últimos {WINDOW_DAYS} dias. Deduplicação: {DEDUPE_RETENTION_DAYS} dias. '
        'Fonte: API Pública do DataJud (CNJ). '
        'Confirmação automática quando o DataJud retorna o nome das partes; '
        'do contrário, o link "abrir" leva à consulta pública do tribunal. '
        'Critérios em <code>assuntos.json</code> e <code>classes.json</code> no repositório.'
        '</div>'
    )

    return "\n".join(blocos)


# =============================================================================
# ENVIO DE E-MAIL
# =============================================================================

def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO

    plain = re.sub(r"<[^>]+>", " ", html_body)
    plain = re.sub(r"\s+", " ", plain).strip()

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    last_err = None
    for attempt in range(3):
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(SMTP_USER, [EMAIL_TO], msg.as_string())
            print(f"E-mail enviado para {EMAIL_TO}")
            return
        except Exception as e:
            last_err = e
            print(f"Tentativa {attempt+1} falhou: {e}")
            time.sleep(5)
    raise RuntimeError(f"Falha ao enviar e-mail: {last_err}")


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def hit_to_row(hit, tribunal):
    numero = get_numero_processo(hit)
    return {
        "numero": numero,
        "tribunal": tribunal,
        "uf": get_uf_from_hit(hit) if tribunal in ("TRF4", "TRF5") else "—",
        "ajuizado": get_data_ajuizamento(hit),
        "classe": get_classe_nome(hit),
        "assuntos": get_assuntos_str(hit),
        "orgao": get_orgao_julgador(hit),
        "link_consulta": consulta_publica_url(numero, tribunal),
        "autores": [],
        "reus": [],
    }


def run():
    assuntos_cfg, classes_cfg = load_configs()
    state = load_reported()
    reported = state["reported"]

    since_dt = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    since_iso = since_dt.strftime("%Y-%m-%d")

    buckets = {"CONFIRMADO": [], "PROVAVEL": [], "VERIFICAR": []}
    falhas = []
    total_candidatos = 0

    targets = [
        ("TRF5", ENDPOINTS["TRF5"], IBGE_RANGES_TRF5),
        ("TRF4", ENDPOINTS["TRF4"], IBGE_RANGES_TRF4),
        ("STF",  ENDPOINTS["STF"],  None),
        ("STJ",  ENDPOINTS["STJ"],  None),
    ]

    for tribunal, endpoint, ibge_ranges in targets:
        try:
            query = build_query(tribunal, since_iso, ibge_ranges, assuntos_cfg)
            hits = fetch_tribunal(tribunal, endpoint, query)
        except Exception as e:
            print(f"[{tribunal}] erro: {e}")
            traceback.print_exc()
            falhas.append(f"{tribunal}: {e}")
            continue

        for hit in hits:
            total_candidatos += 1
            numero = get_numero_processo(hit)
            if not numero:
                continue
            chave = f"{tribunal}:{numero}"
            if chave in reported:
                continue
            if not passa_filtro_classe(hit, classes_cfg):
                continue

            status, autores, reus = validate_hit(hit)
            if status == "DESCARTAR":
                # marca como visto mesmo assim (não reaparece)
                reported[chave] = datetime.now(timezone.utc).isoformat()
                continue

            row = hit_to_row(hit, tribunal)
            row["autores"] = autores
            row["reus"] = reus
            buckets[status].append(row)
            reported[chave] = datetime.now(timezone.utc).isoformat()

    stats = {"total_candidatos": total_candidatos}

    n_total = sum(len(v) for v in buckets.values())
    if n_total == 0 and not falhas:
        print("Nada novo hoje — não envia e-mail.")
        save_reported({"reported": reported})
        return

    subject_date = datetime.now().strftime("%d/%m/%Y")
    subject = f"Monitor Município x União — {subject_date} — {n_total} processo(s)"
    if falhas:
        subject += " (com falhas)"

    html = render_email(buckets, stats, falhas)
    send_email(subject, html)
    save_reported({"reported": reported})


if __name__ == "__main__":
    run()
