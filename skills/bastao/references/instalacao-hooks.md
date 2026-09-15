# Instalar os hooks do bastão

Os hooks são executados pelo harness do Claude Code, não pelo modelo. Eles resolvem o problema de
você estar imerso no trabalho e não perceber a hora de passar o bastão.

## O que cada um faz

| Hook | Quando dispara | O que faz |
|---|---|---|
| `Stop` | toda vez que o Claude termina de responder | estima o tamanho da conversa; passado o limiar, avisa na tela e injeta a instrução de gravar o bastão |
| `SessionStart` | ao abrir ou retomar sessão | procura bastão pendente na pasta e manda ler antes de agir |

O `Stop` avisa **uma vez** por sessão no limiar, e **uma segunda vez** em 1,5 vez o limiar. Não fica repetindo.

## Passo 0: instalar a skill

Copiar a pasta inteira para `~/.claude/skills/bastao/` e deixar o script executável:

```
chmod +x ~/.claude/skills/bastao/bin/bastao.py
```

A skill já funciona nesse ponto, pelos gatilhos verbais da description. Os passos abaixo
acrescentam os hooks, que são o que percebe a hora por você.

## Passo 1: descobrir o JSON com o caminho certo

```
python3 ~/.claude/skills/bastao/bin/bastao.py settings
```

Ele imprime o bloco `hooks` já com o caminho absoluto resolvido para a sua máquina.

## Passo 2: colar em settings.json

Abrir `~/.claude/settings.json` e juntar o bloco `hooks` impresso. Se o arquivo já tiver `hooks`,
acrescentar os eventos `Stop` e `SessionStart` sem apagar o que já existe.

**Antes de editar, copiar o arquivo** (`cp ~/.claude/settings.json ~/.claude/settings.json.bak_AAAA-MM-DD`).
Regra 4.

## Passo 3: ajustar o limiar, se quiser

Padrão: 100.000 tokens estimados. Para mudar, exportar no shell:

```
export BASTAO_LIMIAR_TOKENS=80000
```

O número é uma estimativa por tamanho de arquivo (bytes dividido por 4), não uma contagem real.
Serve para disparar um alarme, não para medir consumo.

## Passo 4: conferir

```
echo '{"session_id":"teste","transcript_path":"/etc/hosts","cwd":"'$PWD'","hook_event_name":"Stop"}' \
  | python3 ~/.claude/skills/bastao/bin/bastao.py hook-stop
```

Não deve dar erro. Com um transcript pequeno, a saída é vazia (nada a avisar).

## Se der problema

Os dois hooks foram escritos para **falhar em silêncio**: qualquer exceção sai com código 0 e sem
saída, para não travar a sessão. Se você suspeitar que um hook está atrapalhando, é só tirar o
bloco do `settings.json`; nada mais depende dele. A skill continua funcionando pelos gatilhos
verbais da description.
