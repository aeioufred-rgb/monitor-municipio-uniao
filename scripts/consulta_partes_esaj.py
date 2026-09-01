#!/usr/bin/env python3
"""
Consulta pública do TJSP (e-SAJ): partes e advogados de uma lista de processos.

Uso pontual via GitHub Actions (workflow consulta-partes.yml). Para cada
número CNJ da lista, consulta o cpopg (1º grau) ou o cposg (2º grau, foro
0000), extrai as partes por polo de participação e os advogados vinculados,
e imprime o resultado em JSON entre marcadores no stdout, além de gravar
partes_resultado.json.

Fonte: consulta pública do e-SAJ (esaj.tjsp.jus.br), dados abertos ao público.
"""

import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

PROCESSOS = [
    "0002666-57.2023.8.26.0619",
    "0011430-66.2025.8.26.0100",
    "0033593-11.2023.8.26.0100",
    "0048386-18.2024.8.26.0100",
    "0048981-22.2021.8.26.0100",
    "0055449-94.2024.8.26.0100",
    "1000093-70.2026.8.26.0248",
    "1000519-18.2026.8.26.0625",
    "1000934-05.2026.8.26.0462",
    "1007837-91.2026.8.26.0224",
    "1009391-88.2026.8.26.0021",
    "1009898-02.2019.8.26.0019",
    "1016038-56.2025.8.26.0564",
    "1018542-40.2023.8.26.0003",
    "1059536-81.2021.8.26.0100",
    "1136320-02.2021.8.26.0100",
    "2061686-85.2025.8.26.0000",
    "2113742-61.2026.8.26.0000",
    "2116789-77.2025.8.26.0000",
    "2215431-85.2025.8.26.0000",
    "2376795-03.2024.8.26.0000",
    "2401598-16.2025.8.26.0000",
]

BASE = "https://esaj.tjsp.jus.br"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Rótulos que aparecem antes do nome de representantes na célula da parte
ROTULOS_REPRESENTANTE = {
    "advogado",
    "advogada",
    "advogados",
    "defensor publico",
    "defensora publica",
    "defensor público",
    "defensora pública",
    "procurador",
    "procuradora",
    "repreleg",
    "representante legal",
    "curador",
    "curadora",
    "curador especial",
    "curadora especial",
    "promotor",
    "promotora",
    "estagiário",
    "estagiária",
    "estagiario",
    "estagiaria",
    "inventariante",
    "liquidante",
    "administrador judicial",
    "administradora judicial",
    "perito",
    "perita",
}

IDS_METADADOS = [
    "classeProcesso",
    "assuntoProcesso",
    "varaProcesso",
    "foroProcesso",
    "juizProcesso",
    "secaoProcesso",
    "orgaoJulgadorProcesso",
    "relatorProcesso",
    "situacaoProcesso",
    "valorAcaoProcesso",
]


def decompor_numero(numero):
    m = re.fullmatch(r"(\d{7})-(\d{2})\.(\d{4})\.8\.26\.(\d{4})", numero)
    if not m:
        raise ValueError(f"Número fora do padrão CNJ/TJSP: {numero}")
    seq, dv, ano, foro = m.groups()
    return f"{seq}-{dv}.{ano}", foro, re.sub(r"\D", "", numero)


def eh_rotulo(prefixo):
    return prefixo.strip().lower().rstrip(":") in ROTULOS_REPRESENTANTE


def parse_celula_parte(td):
    """Separa nome da parte e representantes dentro de td.nomeParteEAdvogado."""
    linhas = [
        t.strip()
        for t in td.get_text("\n", strip=True).replace("\xa0", " ").split("\n")
        if t.strip()
    ]
    nome_parte = []
    representantes = []
    pendente = None  # rótulo aguardando o nome na linha seguinte
    for linha in linhas:
        if pendente is not None:
            representantes.append({"funcao": pendente, "nome": linha})
            pendente = None
            continue
        if ":" in linha:
            prefixo, _, resto = linha.partition(":")
            if eh_rotulo(prefixo):
                resto = resto.strip()
                if resto:
                    representantes.append(
                        {"funcao": prefixo.strip(), "nome": resto}
                    )
                else:
                    pendente = prefixo.strip()
                continue
        nome_parte.append(linha)
    return " ".join(nome_parte), representantes


def parse_partes(soup):
    tabela = soup.find(id="tableTodasPartes") or soup.find(
        id="tablePartesPrincipais"
    )
    partes = []
    if tabela is None:
        return partes
    for tr in tabela.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        participacao = " ".join(
            tds[0].get_text(" ", strip=True).replace("\xa0", " ").split()
        ).rstrip(":")
        nome, representantes = parse_celula_parte(tds[1])
        if not nome and not representantes:
            continue
        partes.append(
            {
                "participacao": participacao,
                "nome": nome,
                "representantes": representantes,
            }
        )
    return partes


def coletar_metadados(soup):
    meta = {}
    for pid in IDS_METADADOS:
        el = soup.find(id=pid)
        if el is not None:
            texto = " ".join(el.get_text(" ", strip=True).split())
            if texto:
                meta[pid] = texto
    return meta


def consultar(sessao, numero):
    seq_dv_ano, foro, digitos = decompor_numero(numero)
    segundo_grau = foro == "0000"
    sistema = "cposg" if segundo_grau else "cpopg"
    resultado = {
        "numero": numero,
        "grau": 2 if segundo_grau else 1,
        "sistema": sistema,
    }

    try:
        sessao.get(f"{BASE}/{sistema}/open.do", headers=HEADERS, timeout=40)
        params = {
            "conversationId": "",
            "cbPesquisa": "NUMPROC",
            "numeroDigitoAnoUnificado": seq_dv_ano,
            "foroNumeroUnificado": foro,
            "dadosConsulta.valorConsultaNuUnificado": digitos,
            "dadosConsulta.valorConsulta": "",
            "dadosConsulta.tipoNuProcesso": "UNIFICADO",
            "tipoNuProcesso": "UNIFICADO",
        }
        r = sessao.get(
            f"{BASE}/{sistema}/search.do",
            params=params,
            headers=HEADERS,
            timeout=60,
        )
        resultado["http"] = r.status_code
        soup = BeautifulSoup(r.content, "html.parser")

        # cposg pode devolver uma listagem de ocorrências; segue o 1º link
        if not soup.find(id="tableTodasPartes") and not soup.find(
            id="tablePartesPrincipais"
        ):
            links = soup.select("a.linkProcesso")
            if links:
                resultado["ocorrencias_listadas"] = len(links)
                href = links[0].get("href", "")
                if href:
                    r2 = sessao.get(
                        BASE + href, headers=HEADERS, timeout=60
                    )
                    soup = BeautifulSoup(r2.content, "html.parser")

        resultado["metadados"] = coletar_metadados(soup)
        resultado["partes"] = parse_partes(soup)

        texto_pagina = soup.get_text(" ", strip=True)
        msg = soup.find(id="mensagemRetorno")
        if msg is not None:
            resultado["mensagem"] = " ".join(
                msg.get_text(" ", strip=True).split()
            )
        if "segredo de justiça" in texto_pagina.lower():
            resultado["segredo_de_justica"] = True
        if not resultado["partes"] and "mensagem" not in resultado:
            titulo = soup.title.get_text(strip=True) if soup.title else ""
            resultado["diagnostico"] = {
                "titulo_pagina": titulo,
                "inicio_texto": texto_pagina[:400],
            }
    except Exception as exc:  # noqa: BLE001 - relatório por processo
        resultado["erro"] = f"{type(exc).__name__}: {exc}"
    return resultado


def main():
    sessao = requests.Session()
    resultados = []
    for i, numero in enumerate(PROCESSOS, 1):
        print(f"[{i}/{len(PROCESSOS)}] {numero}", file=sys.stderr)
        resultados.append(consultar(sessao, numero))
        time.sleep(1.2)

    saida = json.dumps(resultados, ensure_ascii=False, indent=1)
    with open("partes_resultado.json", "w", encoding="utf-8") as f:
        f.write(saida)
    print("===JSON_START===")
    print(saida)
    print("===JSON_END===")


if __name__ == "__main__":
    main()
