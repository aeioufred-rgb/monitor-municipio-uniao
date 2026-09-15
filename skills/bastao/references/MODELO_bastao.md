# Modelo do documento de bastão

Copiar a estrutura abaixo. Seções obrigatórias: 0, 1, 2 e 11. As demais só entram se tiverem conteúdo real.

Zero travessões. Data no formato AAAA-MM-DD.

---

```markdown
# BASTÃO: <título curto do trabalho>

Gravado em: <AAAA-MM-DD HH:MM>
Pasta raiz: <caminho absoluto>
Destino: <sessão nova | agente em paralelo | eu amanhã>
Estado: PENDENTE

## 0. LEIA ANTES DE QUALQUER COISA

- Invocar `regras-fma` antes de escrever, citar ou mexer em arquivo.
- **Este documento não é fonte de nada.** Tudo marcado `[NÃO CONFERIDO]` tem que ser conferido
  na fonte primária, nesta sessão, antes de entrar em qualquer coisa que saia do escritório.
- Não apagar nada. Quarentena datada.
- Mérito e pedido só por proposta.

## 1. IDENTIFICAÇÃO TRAVADA

Copiado verbatim da fonte. Campo sem fonte à vista recebe `[NÃO CONFERIDO]`, nunca um valor plausível.

| Campo | Valor | Fonte |
|---|---|---|
| Tipo de trabalho | caso de bets / Município / contencioso tributário / institucional / código | |
| Cliente ou Município | | |
| Nº CNJ | | |
| Partes | | |
| Vara ou órgão | | |
| Prazo fatal | | |
| Pasta raiz | | |

## 2. OBJETIVO DA PRÓXIMA SESSÃO

Uma frase. Qual é a entrega concreta.

Produto alvo: <peça, nota técnica, minuta, diagnóstico, commit>

## 3. ESTADO

### Feito
### Em andamento
### Bloqueado, e por quê

## 4. FATOS APURADOS

Um por linha, com a fonte ao lado. Sem fonte não é fato apurado, é hipótese: desce para a seção 5.

## 5. HIPÓTESES E SUPOSIÇÕES

Não conferidas. **Não tratar como fato.** Se a próxima sessão confirmar alguma, ela sobe para a 4 com a fonte.

## 6. BECOS SEM SAÍDA

O que já foi tentado e descartado, e o porquê. Esta seção existe para a próxima sessão não refazer
o caminho que esta já andou. É a informação que mais se perde entre sessões.

## 7. DECISÕES PENDENTES

Só o Fred decide. Listar a pergunta, não a resposta.

## 8. SKILLS A INVOCAR

| Skill | Por quê |
|---|---|
| `regras-fma` | sempre, antes de tudo |

## 9. O QUE NÃO FAZER NESTE TRABALHO

- Mérito e pedidos só por proposta.
- <específicos deste trabalho>

## 10. REALIMENTAÇÃO PENDENTE

O que esta sessão apurou e ainda não voltou para a base. O que não realimenta a Usina não está terminado.

| Achado | Base de destino | Estado |
|---|---|---|

## 11. PRIMEIRO PASSO CONCRETO

A primeira ação que a próxima sessão executa. Uma ação, não um plano.

## 12. ARTEFATOS

Ponteiros. Nunca cópia, nunca transcrição, nunca dado pessoal.

| O quê | Caminho |
|---|---|
```

---

## Conferência antes de fechar

- [ ] Nenhum trecho de peça, laudo, extrato ou ficha foi colado
- [ ] Nenhum CPF, RG, conta ou endereço aparece no documento
- [ ] Todo número de CNJ, data, valor e artigo tem fonte ou está `[NÃO CONFERIDO]`
- [ ] Fato e hipótese estão em seções separadas
- [ ] Nenhum travessão fora de citação literal
- [ ] Nenhum mérito ou pedido apresentado como decidido
- [ ] O arquivo está em `00_Bastao/`, e `00_Bastao/` não está dentro de `05_Protocolo`
