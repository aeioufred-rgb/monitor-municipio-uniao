# Monitor diário — Município x União (teses tributárias e financeiras)

Sistema automatizado que consulta a API Pública do DataJud (CNJ) todos os
dias às 9h da manhã (horário de Brasília), identifica processos novos
movidos por municípios contra a União em teses tributárias e financeiras
nos estados de PE, PB, RN, AL e RS (mais STF e STJ), e envia um digest HTML
por e-mail.

## Como funciona

1. Consulta os endpoints DataJud TRF5, TRF4, STF e STJ.
2. Filtra por (a) data de ajuizamento na janela móvel, (b) faixa de código
   IBGE da unidade julgadora, (c) palavras-chave de assuntos do CNJ.
3. Tenta validar a parte ativa (município) e a parte passiva (União) a
   partir do próprio retorno do DataJud.
4. Classifica em três níveis:
   - 🟢 **Confirmado**: autor é município, réu é União/órgão federal.
   - 🟡 **Provável**: autor é município, réu não casou automaticamente.
   - ⚪ **A verificar**: DataJud não retornou as partes — link para
     consulta pública do tribunal.
5. Envia e-mail HTML com tabelas separadas por categoria.
6. Mantém arquivo de deduplicação (`state/reported.json`) para não
   reportar o mesmo processo duas vezes.

## Configuração

### Secrets necessários no GitHub Actions

| Secret | Descrição |
|---|---|
| `DATAJUD_API_KEY` | Chave pública do DataJud (vinda da wiki do CNJ) |
| `SMTP_USER` | E-mail Gmail que envia o digest |
| `SMTP_PASS` | App Password do Gmail (16 caracteres) |
| `EMAIL_TO` | E-mail que recebe o digest |

Opcionais:

| Secret | Default |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |

### Critérios de busca

Editáveis sem mexer no código Python:

- `assuntos.json` — códigos do SGT/CNJ e palavras-chave de assunto
- `classes.json` — classes processuais a incluir/excluir

## Execução

- **Agendada**: todo dia às 12:00 UTC (09:00 BRT).
- **Manual**: aba *Actions* do repositório → workflow "Monitor diário..." → "Run workflow".

## Limitações conhecidas

- O DataJud é alimentado em batch pelos tribunais. Defasagem típica: horas
  a alguns dias. Por isso a janela é de 14 dias, não de 24h.
- Quando o tribunal não popula `partes` no envio ao DataJud, a validação
  automática falha e o processo cai na categoria "A verificar".
- O filtro por IBGE pega o foro, não a origem do município. Município de
  PE que ajuíza ACO no STF aparece pelo endpoint do STF (sem filtro
  geográfico), não pelo TRF5.
- Códigos de assunto do SGT mudam — revalidar palavras-chave
  trimestralmente.

## Estrutura

```
.
├── monitor.py                      Script principal
├── assuntos.json                   Critérios de assunto
├── classes.json                    Critérios de classe
├── requirements.txt                Dependências Python
├── state/
│   └── reported.json               Cache de deduplicação (auto-atualizado)
└── .github/workflows/
    └── diario.yml                  Agendamento do GitHub Actions
```
