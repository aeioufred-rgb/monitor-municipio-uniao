#!/usr/bin/env python3
"""Bastao: localizar a raiz do trabalho, achar o bastao pendente e rodar os hooks.

Subcomandos:
    localizar [caminho]   imprime a raiz do trabalho e a pasta 00_Bastao
    registrar <pasta> <raiz>  fixa a raiz de uma pasta que a deteccao nao acha
    ultimo    [caminho]   imprime o bastao mais recente ainda PENDENTE
    hook-stop             hook Stop: avisa quando a conversa passa do limiar
    hook-sessionstart     hook SessionStart: carrega bastao pendente
    settings              imprime o bloco de hooks para o settings.json

Os dois hooks falham em silencio de proposito: qualquer excecao sai com codigo 0
e sem saida, para nunca travar a sessao do usuario.
"""

import json
import os
import sys
from datetime import datetime, timezone

PASTA_BASTAO = "00_Bastao"
CONFIG = os.path.expanduser("~/.claude/bastao")
RAIZES = os.path.join(CONFIG, "raizes.json")
AVISOS = os.path.join(CONFIG, "avisos")

LIMIAR_PADRAO = 100_000
DIAS_VALIDADE = 45
NIVEIS = (1.0, 1.5)

# Marcadores que identificam a raiz de um trabalho, do mais especifico ao menos.
MARCADORES = (
    "05_Protocolo",
    "01_Instrumentos",
    PASTA_BASTAO,
    "_BASE",
    "_cerebro",
    "_INDICE.md",
    "_LEIA-ME.md",
    "CLAUDE.md",
    ".git",
)

# Bases conhecidas do acervo (skill acervo-fma). Usadas so para rotular o contexto.
BASES_CONHECIDAS = (
    ("Bet", "bets e ludopatia"),
    ("FMA", "escritorio e contencioso tributario"),
    ("Municipios", "teses municipais e casos de Municipio"),
    ("Nucleo de Municipios", "tributario municipal e reforma do consumo"),
    ("Núcleo de Municípios", "tributario municipal e reforma do consumo"),
)


def milhar(n):
    """Separador de milhar no padrao brasileiro."""
    return "{:,}".format(int(n)).replace(",", ".")


def _ler_json(caminho, padrao):
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return padrao


def _gravar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)


def rotular(raiz):
    for fragmento, rotulo in BASES_CONHECIDAS:
        if os.sep + fragmento + os.sep in raiz + os.sep:
            return rotulo
    return "nao identificado"


def localizar_raiz(inicio=None, limite=8):
    """Sobe a partir de inicio ate achar um marcador. Devolve (raiz, motivo) ou (None, None)."""
    atual = os.path.abspath(inicio or os.getcwd())

    registradas = _ler_json(RAIZES, {})
    for prefixo in sorted(registradas, key=len, reverse=True):
        if atual == prefixo or atual.startswith(prefixo + os.sep):
            return registradas[prefixo], "registrada em raizes.json"

    for _ in range(limite):
        for marcador in MARCADORES:
            if os.path.exists(os.path.join(atual, marcador)):
                return atual, "marcador " + marcador
        pai = os.path.dirname(atual)
        if pai == atual:
            break
        atual = pai
    return None, None


def registrar_raiz(prefixo, raiz):
    registradas = _ler_json(RAIZES, {})
    registradas[os.path.abspath(prefixo)] = os.path.abspath(raiz)
    _gravar_json(RAIZES, registradas)


def bastoes(raiz):
    """Lista os bastoes da raiz, do mais novo para o mais antigo."""
    pasta = os.path.join(raiz, PASTA_BASTAO)
    if not os.path.isdir(pasta):
        return []
    itens = []
    for nome in os.listdir(pasta):
        if not nome.endswith(".md"):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            itens.append((os.path.getmtime(caminho), caminho))
        except OSError:
            continue
    itens.sort(reverse=True)
    return [caminho for _, caminho in itens]


def pendente(caminho):
    """Um bastao esta pendente enquanto o cabecalho nao disser CONSUMIDO."""
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as fh:
            cabecalho = fh.read(4000)
    except OSError:
        return False
    return "CONSUMIDO" not in cabecalho.upper()


def ultimo_pendente(raiz):
    for caminho in bastoes(raiz):
        if pendente(caminho):
            return caminho
    return None


def responder(evento, contexto=None, mensagem=None):
    saida = {"hookEventName": evento}
    if contexto:
        saida["additionalContext"] = contexto
    if mensagem:
        saida["systemMessage"] = mensagem
    print(json.dumps({"hookSpecificOutput": saida}, ensure_ascii=False))


# ---------------------------------------------------------------- subcomandos

def cmd_localizar(argv):
    inicio = argv[0] if argv else os.getcwd()
    raiz, motivo = localizar_raiz(inicio)
    if not raiz:
        print("Raiz nao localizada a partir de: " + os.path.abspath(inicio))
        print("Perguntar ao usuario qual e a pasta do trabalho.")
        print("Depois registrar com: bastao.py registrar <pasta-de-trabalho> <raiz>")
        return 1
    destino = os.path.join(raiz, PASTA_BASTAO)
    agora = datetime.now().strftime("%Y-%m-%d_%H%M")
    print("raiz:      " + raiz)
    print("motivo:    " + motivo)
    print("contexto:  " + rotular(raiz))
    print("pasta:     " + destino)
    print("arquivo:   " + os.path.join(destino, "bastao_" + agora + ".md"))
    anterior = ultimo_pendente(raiz)
    if anterior:
        print("pendente:  " + anterior)
    return 0


def cmd_registrar(argv):
    if len(argv) != 2:
        print("uso: bastao.py registrar <pasta-de-trabalho> <raiz>")
        return 2
    registrar_raiz(argv[0], argv[1])
    print("registrado em " + RAIZES)
    return 0


def cmd_ultimo(argv):
    inicio = argv[0] if argv else os.getcwd()
    raiz, _ = localizar_raiz(inicio)
    if not raiz:
        print("Raiz nao localizada.")
        return 1
    caminho = ultimo_pendente(raiz)
    if not caminho:
        print("Nenhum bastao pendente em " + os.path.join(raiz, PASTA_BASTAO))
        return 1
    print(caminho)
    return 0


def cmd_hook_stop(_argv):
    entrada = json.loads(sys.stdin.read() or "{}")
    transcript = entrada.get("transcript_path") or ""
    sessao = entrada.get("session_id") or "sem-id"
    if not transcript or not os.path.exists(transcript):
        return 0

    try:
        limiar = int(os.environ.get("BASTAO_LIMIAR_TOKENS", LIMIAR_PADRAO))
    except ValueError:
        limiar = LIMIAR_PADRAO

    estimado = os.path.getsize(transcript) // 4
    marcador = os.path.join(AVISOS, sessao + ".json")
    ja_avisado = _ler_json(marcador, {}).get("nivel", 0)

    nivel = 0
    for indice, fator in enumerate(NIVEIS, start=1):
        if estimado >= limiar * fator:
            nivel = indice
    if nivel == 0 or nivel <= ja_avisado:
        return 0

    _gravar_json(marcador, {"nivel": nivel, "em": datetime.now(timezone.utc).isoformat()})

    contexto = (
        "A conversa passou de {} tokens estimados (limiar {}). Qualidade de resposta "
        "cai perto do limite de compactacao. Ofereca ao usuario, em uma linha, gravar o "
        "bastao agora com a skill `bastao`, para continuar numa sessao limpa. Se ele "
        "aceitar ou ja estiver encerrando, grave. Se ele disser para seguir, siga sem "
        "insistir e nao volte a oferecer."
    ).format(milhar(estimado), milhar(limiar))
    mensagem = "bastao: ~" + milhar(estimado) + " tokens nesta sessao. Considere /bastao."
    responder("Stop", contexto, mensagem)
    return 0


def cmd_hook_sessionstart(_argv):
    entrada = json.loads(sys.stdin.read() or "{}")
    cwd = entrada.get("cwd") or os.getcwd()
    raiz, _ = localizar_raiz(cwd)
    if not raiz:
        return 0
    caminho = ultimo_pendente(raiz)
    if not caminho:
        return 0

    idade = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(caminho))).days
    if idade > DIAS_VALIDADE:
        return 0

    contexto = (
        "Existe um bastao PENDENTE para este trabalho, gravado ha {} dia(s):\n"
        "  {}\n"
        "Leia o arquivo inteiro antes de agir. Ele nao e fonte: todo campo marcado "
        "[NAO CONFERIDO] tem que ser conferido na fonte primaria antes de uso, e a secao "
        "de hipoteses nao pode ser tratada como fato. Invoque `regras-fma` antes de "
        "escrever ou citar qualquer coisa. Ao concluir o trabalho dele, marque CONSUMIDO "
        "no cabecalho do bastao, sem apagar o arquivo."
    ).format(idade, caminho)
    mensagem = "bastao pendente: " + os.path.basename(caminho)
    responder("SessionStart", contexto, mensagem)
    return 0


def cmd_settings(_argv):
    script = os.path.abspath(__file__)
    bloco = {
        "hooks": {
            "Stop": [{"hooks": [{
                "type": "command", "command": "python3",
                "args": [script, "hook-stop"], "timeout": 10}]}],
            "SessionStart": [{"hooks": [{
                "type": "command", "command": "python3",
                "args": [script, "hook-sessionstart"], "timeout": 10}]}],
        }
    }
    print(json.dumps(bloco, ensure_ascii=False, indent=2))
    return 0


COMANDOS = {
    "localizar": cmd_localizar,
    "registrar": cmd_registrar,
    "ultimo": cmd_ultimo,
    "hook-stop": cmd_hook_stop,
    "hook-sessionstart": cmd_hook_sessionstart,
    "settings": cmd_settings,
}


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] not in COMANDOS:
        print(__doc__)
        return 2
    return COMANDOS[argv[0]](argv[1:])


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando.startswith("hook-"):
        # Hook nunca pode quebrar a sessao do usuario.
        try:
            sys.exit(main() or 0)
        except Exception:
            sys.exit(0)
    sys.exit(main())
