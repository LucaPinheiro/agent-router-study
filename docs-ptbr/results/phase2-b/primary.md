# Análise primária da Parte B [C]: H1-L, H2-L, H3-L no `test_l`

> Tradução pt-BR de [`docs/results/phase2-b/primary.md`](../../../docs/results/phase2-b/primary.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

Gerado por `scripts/analysis/phase2_b.py` (offline). ITT (uma falha de infra ou de parse conta como erro); unidade = caso, com as repetições tiradas a média primeiro; bootstrap pareado por cluster sobre os ids de caso, 10 000 reamostragens, seed 20260930; p = sign-flip no nível do caso (NI: deslocamento +3 pp, unilateral); Holm step-down entre H1-L..H3-L (α 0.05). Uma hipótese cuja run falta ou não está COMPLETE é **NÃO RODADA** (nunca imputada) e entra no Holm com p = 1. Conjunta de roteamento: scorer legacy e0eef1fb0073; e2e: `e2e_success_sym` (scorers_sym 5ad0f65296e4).

- **H1-L (bilateral, e2e, scorer simétrico):** e2e_success_sym(E9-L) − e2e_success_sym(E0-L); afirmação direcional só se o IC excluir 0.
- **H2-L (NI, 3 pp; reespecificada pela atualização de restrição de 2026-10-02):** Conjunta(E6m Ministral) − Conjunta(E6 Haiku 4.5) > −3 pp.
- **H3-L (NI, 3 pp):** Conjunta(E4 Jev) − Conjunta(E6 Haiku 4.5) > −3 pp.

## Família primária: ITT [C]

| id | run | referência | tipo | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (família) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| H1-L | E9@e2e | E0@e2e | two_sided | 300 | -0.3 [-4.0, 3.3] | 16/17 p=1 | 1 | 1 | não | IC inclui 0 (sem afirmação direcional) |
| H2-L | E6m | E6 | non_inferiority (margem 3 pp) | 300 | -2.7 [-7.0, 1.7] | 18/26 p=0.291 | 0.4398 | 0.8795 | não | não inferioridade NÃO demonstrada |
| H3-L | E4 | E6 | non_inferiority (margem 3 pp) | 300 | 2.9 [-0.7, 6.6] | 26/12 p=0.0336 | 0.0008999 | 0.0027 | sim | não inferior (limite inferior do IC > -3 pp) |

## H1-L com o scorer legacy assimétrico (SENSIBILIDADE, não testada) [E]

| id | run | referência | tipo | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (família) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| H1-L legacy | E9@e2e | E0@e2e | two_sided | 300 | -3.3 [-7.7, 1.0] | 18/28 p=0.184 | 0.1877 | - (não testada) | - | IC inclui 0 (sem afirmação direcional) |

| braço | turnos | falha legacy → sucesso sym | sucesso legacy → falha sym |
|---|---|---|---|
| E9 | 300 | 17 | 0 |
| E0 | 300 | 8 | 0 |

Casos cujo veredito pareado (vitória só do E9-L / só do E0-L / empate) difere entre os dois scorers: **21**.

## Estimativas co-primárias [C]

| estimativa | razão | o quê | numerador (US$/1k ou ms) [IC 95%] | denominador [IC 95%] | razão [IC 95%] | n casos pareados |
|---|---|---|---|---|---|---|
| H1-L co-primária | custo por turno E9-L / E0-L | US$/turno roteamento + executor, regime observado | 11.192 [10.390, 12.007] | 10.164 [9.407, 10.964] | 1.101 [1.014, 1.196] | 300 |
| H2-L co-primária | latência p95 E6m / E6 Haiku | latência de roteamento quente, benchmark dedicado (lat-l-*) | 1383 [1360, 1410] | 5278 [4881, 7287] | 0.262 [0.189, 0.283] | 96 |

## Sensibilidades das primárias (prereg-v2 §3, NÃO testadas; sem ajuste) [E]

| id | variante | n casos | Δ pp [IC 95%] | veredito do IC |
|---|---|---|---|---|
| H1-L | conjunta só com o primeiro rótulo (H2-L, H3-L) | 300 | -0.3 [-4.0, 3.3] | IC inclui 0 (sem afirmação direcional) |
| H2-L | conjunta só com o primeiro rótulo (H2-L, H3-L) | 300 | -6.0 [-10.0, -2.0] | não inferioridade NÃO demonstrada |
| H3-L | conjunta só com o primeiro rótulo (H2-L, H3-L) | 300 | 0.6 [-3.1, 4.2] | não inferioridade NÃO demonstrada |
| H1-L | sem os ambiguo | 240 | -2.1 [-4.6, 0.4] | IC inclui 0 (sem afirmação direcional) |
| H2-L | sem os ambiguo | 240 | -5.0 [-9.2, -0.8] | não inferioridade NÃO demonstrada |
| H3-L | sem os ambiguo | 240 | -0.1 [-3.8, 3.3] | não inferioridade NÃO demonstrada |
| H1-L | só ambiguo (reportado à parte) | 60 | 6.7 [-8.3, 21.7] | IC inclui 0 (sem afirmação direcional) |
| H2-L | só ambiguo (reportado à parte) | 60 | 6.7 [-6.7, 20.0] | não inferioridade NÃO demonstrada |
| H3-L | só ambiguo (reportado à parte) | 60 | 15.0 [4.4, 26.1] | não inferior (limite inferior do IC > -3 pp) |
| H1-L | sem os casos sinalizados pela auditoria (85 sinalizados) | 215 | -1.9 [-6.0, 2.3] | IC inclui 0 (sem afirmação direcional) |
| H2-L | sem os casos sinalizados pela auditoria (85 sinalizados) | 215 | -4.7 [-9.3, 0.0] | não inferioridade NÃO demonstrada |
| H3-L | sem os casos sinalizados pela auditoria (85 sinalizados) | 215 | 2.2 [-1.4, 5.9] | não inferior (limite inferior do IC > -3 pp) |
| H1-L | casos sem erro nas duas runs | 300 | -0.3 [-4.0, 3.3] | IC inclui 0 (sem afirmação direcional) |
| H2-L | casos sem erro nas duas runs | 299 | -2.7 [-7.0, 1.7] | não inferioridade NÃO demonstrada |
| H3-L | casos sem erro nas duas runs | 299 | 3.1 [-0.4, 6.7] | não inferior (limite inferior do IC > -3 pp) |

## Resultado principal por run (ITT, IC 95% por bootstrap por cluster) [E]

| braço | run | métrica | linhas | linhas de erro | % [IC 95%] |
|---|---|---|---|---|---|
| E6m | l-e6m-ministral-canonical-routing-r1 | conjunta (legacy) | 300 | 1 | 79.3 [74.7, 84.0] |
| E6 | l-e6-haiku-canonical-routing-r1 | conjunta (legacy) | 300 | 0 | 82.0 [77.7, 86.0] |
| E4 | l-e4-jev-canonical-routing-r3 | conjunta (legacy) | 900 | 1 | 84.9 [81.1, 88.4] |
| E0-L e2e | l-e0-native-e2e-r1 | e2e_success_sym | 300 | 0 | 57.3 [51.7, 62.7] |
| E0-L e2e | l-e0-native-e2e-r1 | e2e_success legacy | 300 | 0 | 54.7 [49.0, 60.3] |
| E9-L e2e | l-e9-tuned-e2e-r1 | e2e_success_sym | 300 | 0 | 57.0 [51.3, 62.3] |
| E9-L e2e | l-e9-tuned-e2e-r1 | e2e_success legacy | 300 | 0 | 51.3 [45.7, 57.0] |

## Leitura

- Regra de decisão de NI: não inferior sse o limite inferior do IC 95% pareado bilateral de Δ fica acima de −3 pp; o p sign-flip ajustado por Holm testa H0: Δ ≤ −3 pp. Os dois são mostrados; a regra do IC é a decisão pré-registrada.
- H1-L: bilateral; o número do scorer legacy é uma sensibilidade reportada lado a lado, nunca a decisão.

## Inventário de runs e proveniência

Todos os braços registrados; um que falta é reportado como NÃO RODADO. Proveniência verificada em toda linha (hashes de catálogo, scorer, prompt e dataset; scorer/dataset/tools do cabeçalho de proveniência; um config hash por arquivo; arquivos legacy e sym a partir dos mesmos bytes brutos).

| tipo | chave | arquivo | linhas | casos / split | linhas de erro | arquivo sym | status |
|---|---|---|---|---|---|---|---|
| routing | E1 | results/rescored/l-e1-regex-routing-r1.jsonl | 300 | 300 / 300 | 0 | n/a | usada |
| routing | E2 | results/rescored/l-e2-bm25-routing-r1.jsonl | 300 | 300 / 300 | 0 | n/a | usada |
| routing | E3 | results/rescored/l-e3-embedding-routing-r1.jsonl | 300 | 300 / 300 | 0 | n/a | usada |
| routing | E3c | l-e3c-cohere-routing-r1 | - | - | - | - | **NÃO RODADA** (sem arquivo) |
| routing | E3t | l-e3t-titan-routing-r1 | - | - | - | - | **NÃO RODADA** (sem arquivo) |
| routing | E10 | results/rescored/l-e10-classifier-routing-r1.jsonl | 300 | 300 / 300 | 0 | n/a | usada |
| routing | E10c | l-e10c-cohere-routing-r1 | - | - | - | - | **NÃO RODADA** (sem arquivo) |
| routing | E11 | results/rescored/l-e11-hybrid-routing-r1.jsonl | 300 | 300 / 300 | 0 | n/a | usada |
| routing | E4 | results/rescored/l-e4-jev-canonical-routing-r3.jsonl | 900 | 300 / 300 | 1 | n/a | usada |
| routing | E6 | results/rescored/l-e6-haiku-canonical-routing-r1.jsonl | 300 | 300 / 300 | 0 | n/a | usada |
| routing | E6m | results/rescored/l-e6m-ministral-canonical-routing-r1.jsonl | 300 | 300 / 300 | 1 | n/a | usada |
| routing | E6n | results/rescored/l-e6n-nemotron-canonical-routing-r1.jsonl | 300 | 300 / 300 | 11 | n/a | usada |
| routing | E7 | results/rescored/l-e7-tuned-routing-r3.jsonl | 900 | 300 / 300 | 0 | n/a | usada |
| routing | E9 | results/rescored/l-e9-tuned-routing-r3.jsonl | 900 | 300 / 300 | 0 | n/a | usada |
| routing | E12 | results/rescored/x-l-e12-hybrid-tuned-routing-r3.jsonl | 900 | 300 / 300 | 0 | n/a | usada |
| e2e | E0 | results/rescored/l-e0-native-e2e-r1.jsonl | 300 | 300 / 300 | 0 | sim | usada |
| e2e | E9 | results/rescored/l-e9-tuned-e2e-r1.jsonl | 300 | 300 / 300 | 0 | sim | usada |
| e2e | E9-full | results/rescored/l-e9-fullskill-e2e-r1.jsonl | 300 | 300 / 300 | 0 | sim | usada |
| variance | E0 | results/rescored/l-e0-native-e2e-rep2-60.jsonl | 60 | 60 / 300 | 0 | sim | usada |
| variance | E9 | results/rescored/l-e9-tuned-e2e-rep2-60.jsonl | 60 | 60 / 300 | 0 | sim | usada |
| repeat | E1 | results/rescored/l-e1-regex-routing-repeat20.jsonl | 40 | 20 / 300 | 0 | n/a | usada |
| repeat | E6 | results/rescored/l-e6-haiku-canonical-rep2-60.jsonl | 120 | 60 / 300 | 0 | n/a | usada |
| repeat | E6m | results/rescored/l-e6m-ministral-canonical-repeat50.jsonl | 100 | 50 / 300 | 0 | n/a | usada |
| repeat | E6n | results/rescored/l-e6n-nemotron-canonical-repeat50.jsonl | 100 | 50 / 300 | 4 | n/a | usada |
| x2 | E1 | results/rescored/l-x2-small-e1-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| x2 | E2 | results/rescored/l-x2-small-e2-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| x2 | E3 | results/rescored/l-x2-small-e3-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| x2 | E10 | results/rescored/l-x2-small-e10-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| x2 | E11 | l-x2-small-e11-routing-r1 | - | - | - | - | **NÃO RODADA** (sem arquivo) |
| x2 | E4 | results/rescored/l-x2-small-e4-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| x2 | E6m | results/rescored/l-x2-small-e6m-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| x2 | E6 | results/rescored/l-x2-small-e6-routing-r1.jsonl | 114 | 114 / 300 | 0 | n/a | usada |
| lat | regex | lat-l-regex-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | bm25 | lat-l-bm25-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | embedding | lat-l-embedding-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | e3c | lat-l-e3c-b1..4 | - | - | - | n/a | **NÃO RODADA** |
| lat | e3t | lat-l-e3t-b1..4 | - | - | - | n/a | **NÃO RODADA** |
| lat | classifier | lat-l-classifier-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | hybrid | lat-l-hybrid-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | jev | lat-l-jev-b1..4 | 100 | - | 1 | n/a | usada (4 blocos) |
| lat | haiku | lat-l-haiku-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | e6m | lat-l-e6m-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| lat | e6n | lat-l-e6n-b1..4 | 100 | - | 5 | n/a | usada (4 blocos) |
| lat | e7 | lat-l-e7-b1..4 | 100 | - | 1 | n/a | usada (4 blocos) |
| lat | e9 | lat-l-e9-b1..4 | 100 | - | 0 | n/a | usada (4 blocos) |
| manifest | - | runs sem mapeamento: l-shadow-tuned-routing-r3 |  |  |  |  | ignorada |

| arquivo | config hash | catálogo | scorer legacy | scorer sym | prompt | verificação |
|---|---|---|---|---|---|---|
| l-e1-regex-routing-r1.jsonl | 9edc10d85a4e | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e2-bm25-routing-r1.jsonl | 047a16011d05 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e3-embedding-routing-r1.jsonl | 3cd09a609c93 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e10-classifier-routing-r1.jsonl | 61260135d35a | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e11-hybrid-routing-r1.jsonl | 0078bcc597f8 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e4-jev-canonical-routing-r3.jsonl | d8d2f8940050 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e6-haiku-canonical-routing-r1.jsonl | 8b7b8fb00143 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e6m-ministral-canonical-routing-r1.jsonl | 1ce8c6004c5f | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e6n-nemotron-canonical-routing-r1.jsonl | ae768b0a8656 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e7-tuned-routing-r3.jsonl | babfafa1bdae | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e9-tuned-routing-r3.jsonl | 8236c879738c | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| x-l-e12-hybrid-tuned-routing-r3.jsonl | fd13e06c82a4 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e0-native-e2e-r1.jsonl | 93c7c3ea1e02 | bc7cd75fce87 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| l-e9-tuned-e2e-r1.jsonl | 8236c879738c | bc7cd75fce87 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| l-e9-fullskill-e2e-r1.jsonl | 2741f7281d8b | bc7cd75fce87 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| l-e0-native-e2e-rep2-60.jsonl | 93c7c3ea1e02 | bc7cd75fce87 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| l-e9-tuned-e2e-rep2-60.jsonl | 8236c879738c | bc7cd75fce87 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| l-e1-regex-routing-repeat20.jsonl | 9edc10d85a4e | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e6-haiku-canonical-rep2-60.jsonl | 8b7b8fb00143 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e6m-ministral-canonical-repeat50.jsonl | 1ce8c6004c5f | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-e6n-nemotron-canonical-repeat50.jsonl | ae768b0a8656 | bc7cd75fce87 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e1-routing-r1.jsonl | 2da827d0effb | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e2-routing-r1.jsonl | 7bb5a5960490 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e3-routing-r1.jsonl | 73f81417a487 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e10-routing-r1.jsonl | 70374caa4b59 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e4-routing-r1.jsonl | acd7ff96155b | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e6m-routing-r1.jsonl | 0d8fbee553f3 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| l-x2-small-e6-routing-r1.jsonl | f6c0edce210b | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e1-regex-routing-r1.jsonl (test-v2, X1) | 2da827d0effb | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e2-bm25-routing-r1.jsonl (test-v2, X1) | 7bb5a5960490 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2a-e3t-titan-routing-r1.jsonl (test-v2, X1) | 73f81417a487 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2a-e10t-titan-routing-r1.jsonl (test-v2, X1) | 70374caa4b59 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e11-hybrid-routing-r1.jsonl (test-v2, X1) | 68cc177d37b0 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e4-jev-canonical-routing-r3.jsonl (test-v2, X1) | acd7ff96155b | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e6-haiku-canonical-routing-r1.jsonl (test-v2, X1) | f6c0edce210b | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2a-e6m-ministral-canonical-routing-r1.jsonl (test-v2, X1) | 0d8fbee553f3 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2a-e6n-nemotron-canonical-routing-r1.jsonl (test-v2, X1) | efb00ce5b9f8 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e7-tuned-routing-r3.jsonl (test-v2, X1) | 4fbfd7133b32 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e9-tuned-routing-r3.jsonl (test-v2, X1) | 8f5f721c9158 | 128584617807 | e0eef1fb0073 | - | c61ad0a7b7f8 | ok |
| v2-e0-native-e2e-r1.jsonl (test-v2, X1) | 93c7c3ea1e02 | 128584617807 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| v2-e9-tuned-e2e-r1.jsonl (test-v2, X1) | 8f5f721c9158 | 128584617807 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
| x-e9-fullskill-e2e-r1.jsonl (test-v2, X1) | 3011c95c0e12 | 128584617807 | e0eef1fb0073 | 5ad0f65296e4 | c61ad0a7b7f8 | ok |
