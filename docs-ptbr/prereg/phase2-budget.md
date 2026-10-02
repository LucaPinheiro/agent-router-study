# Marca de orçamento da fase 2 (plano T0.2)

> Tradução pt-BR de [`docs/prereg/phase2-budget.md`](../../docs/prereg/phase2-budget.md). Em caso de divergência, vale o original em inglês.

Todo custo da fase 2 é medido contra esta marca inicial. Gasto da fase 2 = total do ledger − marca.
O ledger é `results/spend_ledger.jsonl`, lido com `uv run study budget`.

## Marca inicial

| provedor | marca (US$) | ledger na marca |
|---|---|---|
| AWS (Bedrock) | **52.11** | 52.1147 |
| OpenRouter | **5.83** | 5.8345 |

A marca é o ledger em **2026-10-01T23:42:38Z**: a última chamada da fase 1 antes de o trabalho da
fase 2 começar. Recalcular a soma acumulada do ledger até essa linha dá 52.1147 / 5.8345, o que
bate com a marca na precisão de centavos.

## Tetos (plano §5)

| | teto da fase 2 (US$) | teto do ledger = marca + teto |
|---|---|---|
| AWS | 29.00 | **81.11** |
| OpenRouter | 9.00 | **14.83** |
| total | 38.00 (reserva de US$ 2 abaixo do limite de US$ 40) | |

O teto da conta do OpenRouter nas configurações ainda é **9.00 absoluto**, o valor da fase 1. O
trabalho da fase 2 no OpenRouter para, portanto, em cerca de US$ 3.16 de gasto da fase 2, a menos
que esse teto seja elevado ao teto do ledger (14.83) quando a recarga humana chegar. O portão
rígido do plano (R4) diz que o T4.1 não começa até o saldo ser ≥ 9.5.

## Tetos por item (plano §5, US$ esperados)

| ID | Item | AWS | OR |
|---|---|---|---|
| A1 | Ajuste no dev da Parte A, 8B ×2 (151) | 0.20 | – |
| A2 | Embeddings da Parte A (grade no dev + test-v2 + latência) | 0.10 | – |
| A3 | test-v2 da Parte A, 8B ×2 (349 + rep2 50) | 0.50 | – |
| A4 | Latência da Parte A (6 novos × 100 + âncoras) | 0.65 | 0.08 |
| A5 | Reescore simétrico da fase 1 (offline) | 0 | 0 |
| B1 | Geração do dev-L + test-L (450 aceitos) | – | 2.00 |
| B2 | Auditoria do dev-L + test-L | – | 2.25 |
| B3 | Smoke do host + smoke e2e no dev-L (5 + 20 turnos) | 0.45 | – |
| B4 | dev-L Haiku P0 1 rep | 1.17 | – |
| B5 | dev-L Jev P0 1 rep (shadow) | – | 0.19 |
| B6 | dev-L Sonnet shadow 1 rep (só limiares) | 1.35 | – |
| B7 | dev-L 8B ×2 + embeddings de nuvem | 0.28 | – |
| B8 | Validação e2e no dev-L, E0-L + E9-L (40 + 40) | 0.81 | – |
| B9 | test-L Jev E4 3 reps | – | 1.12 |
| B10 | test-L Haiku 1 rep + rep2 60 | 2.81 | – |
| B11 | test-L 8B ×2, 1 rep + rep2 50 | 0.66 | – |
| B12 | test-L E9-L roteamento 3 reps | 1.40 | – |
| B13 | test-L E0-L e2e (H1) | 3.39 | – |
| B14 | test-L E9-L e2e (H1) | 2.69 | – |
| B15 | test-L E9-L-fullskill e2e (S1) | 2.80 | – |
| B16 | Variância do executor rep2 em 60 | 1.22 | – |
| B17 | Latência no test-L | 1.17 | 0.12 |
| B18 | Subconjunto pareado de tamanho de catálogo (~90 casos) | 0.55 | 0.08 |
| | **Total esperado** | **22.20** | **5.84** |

US$ 28.0 esperados no total, ou 35.1 com 25% de contingência. Se um teto for atingido, o guarda
recusa a run e nada é reordenado. Ordem de corte: B16, depois B15, depois B18-Haiku, depois as
âncoras de A4/B17.

## Captura do ledger no momento da escrita (2026-10-01, `uv run study budget`)

```
aws         (bedrock) spent $52.2938 of cap $90.00
openrouter  (openrouter) spent $5.8395 of cap $9.00
```

Gasto desde a marca (linhas acumuladas do ledger depois de 2026-10-01T23:42:38Z):

| provedor | run | chamadas | US$ | conta como |
|---|---|---|---|---|
| bedrock | `obs-graph-check` (verificação do Langfuse da fase 1, dev) | 4 | 0.0356 | cauda da fase 1 |
| bedrock | `it-trace-1790904935` (teste de integração) | 8 | 0.0380 | cauda da fase 1 |
| openrouter | `it-trace-1790904935` | 4 | 0.0050 | cauda da fase 1 |
| bedrock | chamadas de smoke da fase 2 (roteadores 8B, Cohere/Titan, sem nome de run) | 765 | 0.0045 | fase 2 (T0.3/T2.1) |
| bedrock | `p2-dev-e6c_llm_ministral_bedrock` | 302 | 0.0677 | fase 2 (A1) |
| bedrock | `p2-dev-e6d_llm_nemotron_bedrock` | 301 | 0.0341 | fase 2 (A1) |

A captura difere da marca só por essas linhas: 52.1147 + 0.0736 + 0.1063 = 52.2946 ≈
52.2938, dentro de US$ 0.001 (as somas por grupo são arredondadas a 4 casas). No OpenRouter,
5.8345 + 0.0050 = 5.8395. O gasto da fase 2 até aqui é AWS US$ 0.106 e OpenRouter US$ 0. Os
US$ 0.079 da cauda da fase 1 depois da marca também contam contra os tetos da fase 2, porque os
tetos são medidos a partir da marca.
