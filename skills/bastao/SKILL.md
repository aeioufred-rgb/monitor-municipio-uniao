---
name: "bastao"
description: "Passar o bastão: gravar o estado de um trabalho num documento para outra sessão, outro agente ou para você amanhã, e retomar a partir dele. Disparar quando o usuário pedir /bastao, e também por conta própria quando ele sinalizar parada, transferência ou retomada: \"vamos parar por aqui\", \"paro por hoje\", \"continuo amanhã\", \"retoma amanhã\", \"salva onde paramos\", \"abre outra sessão pra isso\", \"passa isso pra outro agente\", \"vamos dividir esse trabalho\", \"o contexto tá estourando\", \"essa sessão já tá longa\", \"me lembra onde eu parei\", \"o que a gente estava fazendo\". Serve a caso de bets, Município, contencioso tributário, material institucional e código. Grava em 00_Bastao na raiz do trabalho, nunca em pasta temporária."
---

# Bastão

Passa o estado de um trabalho adiante sem perder o que foi apurado e sem promover a fato o que era suposição.

**Bastão não é arquivo de trabalho, é documento de trânsito.** Ele não substitui a base, não copia a base e não vira espelho da base. Se o que você ia escrever no bastão já existe numa base, o bastão aponta o caminho e para por aí.

## Antes de qualquer coisa

Invocar `regras-fma`. O bastão é texto redigido e carrega número de processo, data, valor e dispositivo legal. As regras 2 (nada inventado), 3 (verbatim) e 4 (reversibilidade) valem inteiras, e a regra 1 também: zero travessões.

## Dois modos

| Modo | Quando | O que faz |
|---|---|---|
| **GRAVAR** (padrão) | fim de sessão, troca de agente, divisão de trabalho | escreve o documento |
| **RETOMAR** | início de sessão, "onde eu parei" | lê o bastão mais recente e reconstitui o estado |

Se o pedido for ambíguo, decidir pelo verbo do usuário. "Salva", "passa", "paro": GRAVAR. "Retoma", "continua", "onde paramos": RETOMAR.

---

## Modo GRAVAR

### Passo 1: localizar a raiz do trabalho

```
python3 <pasta desta skill>/bin/bastao.py localizar
```

O script sobe da pasta atual procurando marcador de trabalho (`_BASE`, `_INDICE.md`, `CLAUDE.md`, `05_Protocolo`, `_cerebro`, `.git`, `00_Bastao`) e consulta os caminhos conhecidos do acervo.

Se não achar, **perguntar ao usuário qual é a pasta**. Nunca chutar, nunca gravar em pasta temporária sem dizer isso na cara dele. A resposta fica registrada em `~/.claude/bastao/raizes.json` e não se pergunta de novo.

Se a pasta do trabalho não estiver montada na sessão, **parar e pedir a conexão**, como manda `inicial-bets`. Bastão escrito sem a pasta à vista é bastão de memória, e memória não é fonte.

### Passo 2: onde grava

```
<raiz>/00_Bastao/bastao_AAAA-MM-DD_HHMM.md
```

Três regras que não se negociam:

1. **Nunca sobrescrever bastão anterior.** Arquivo novo a cada vez, com carimbo de hora.
2. **Nunca apagar bastão.** Quando consumido, marca-se `CONSUMIDO em <data>` no cabeçalho. Não se remove.
3. **`00_Bastao/` é interno.** Não entra em `05_Protocolo`, não sobe ao PJe, não vai para cliente, não entra em índice de juntada. Em caso de bets, conferir isso antes de fechar a pasta de protocolo.

### Passo 3: preencher pelo modelo

Modelo em `references/MODELO_bastao.md`.

Seções **obrigatórias**: 0 (leia antes), 1 (identificação travada), 2 (objetivo) e 11 (primeiro passo). As demais só entram se tiverem conteúdo real. Seção vazia sai do documento; não deixar cabeçalho órfão.

### As cinco regras do conteúdo

1. **Ponteiro, nunca cópia.** Não colar trecho de peça, laudo, extrato, ficha de legislação ou acórdão. Caminho do arquivo e ponto.
2. **Sem fonte, `[NÃO CONFERIDO]`.** Vale para número de CNJ, data de prazo, valor, artigo. Preferir o campo marcado a um campo plausível. Campo plausível é o modo como o erro entra.
3. **Fato apurado e hipótese vão em listas separadas e rotuladas.** É a seção que impede a próxima sessão de tratar palpite como coisa julgada.
4. **Nenhum dado pessoal no bastão.** CPF, RG, conta bancária, endereço, extrato de apostas: aponta o arquivo que contém, não transcreve. O documento circula entre sessões e agentes.
5. **Mérito e pedido entram como proposta, nunca como decidido.** Regra 5 de `regras-fma`. O bastão pode dizer "proposta de pedido X, pendente de aprovação". Não pode dizer "o pedido é X".

### Passo 4: realimentação

Antes de fechar, preencher a seção 10. "O que não realimenta a Usina não está terminado" (`inicial-bets`). Se a sessão produziu achado que serve a outra base, isso é entrada de `acervo-fma`, e o bastão registra que está pendente.

### Passo 5: relatar

Dizer ao usuário o caminho completo do arquivo gravado e as seções que ficaram com `[NÃO CONFERIDO]`. Essa lista é a dívida que ele está carregando para a próxima sessão.

---

## Modo RETOMAR

1. Rodar `python3 <skill>/bin/bastao.py ultimo` para achar o bastão mais recente não consumido.
2. **Ler o bastão inteiro antes de agir.**
3. Invocar as skills que a seção 8 indica.
4. **Conferir na fonte todo campo marcado `[NÃO CONFERIDO]` antes de usar.** O bastão não é fonte de nada. Ele é um índice do que a sessão anterior sabia.
5. Tratar a seção 5 (hipóteses) como hipótese. Não promover a fato sem conferir.
6. Ler a seção 6 (becos sem saída) antes de propor caminho. Ela existe para você não refazer o que já foi descartado.
7. Ao terminar, marcar `CONSUMIDO em <data>` no cabeçalho do bastão lido. Não apagar.

---

## Automação

A skill dispara sozinha pelos gatilhos verbais da description. Para o caso em que você está imerso e não percebe a hora, há dois hooks em `bin/bastao.py`. Instalação em `references/instalacao-hooks.md`.

| Hook | O que faz |
|---|---|
| `Stop` | mede o tamanho da conversa e, passado o limiar, avisa e manda gravar o bastão |
| `SessionStart` | ao abrir sessão numa pasta que tem bastão pendente, carrega o caminho e manda ler |

O hook injeta instrução, não força chamada de ferramenta. Na prática funciona; não é garantia. O que é determinístico é o aviso na tela.
