# Tabelas de estimação da Parte B [E] (prereg-v2 §3 'Estimation only'; ICs, sem testes) no `test_l`

> Tradução pt-BR de [`docs/results/phase2-b/estimation.md`](../../../docs/results/phase2-b/estimation.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

Gerado por `scripts/analysis/phase2_b.py`. ITT; ICs 95% = bootstrap por cluster sobre os ids de caso (10k, seed 20260930).

## A. Por estratégia [E] (só roteamento, ITT; % com IC 95% por bootstrap por cluster)

| roteador | status | linhas | reps | linhas de erro | skill % | tool % dado skill certa | conjunta % (métrica primária) | conjunta só primeiro rótulo % (estrita) | abstain_correct % | recall@1 | recall@2 | recall@3 | precisão da abstenção % (n abstidos) | recall da abstenção % (n esperados) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 regex | estimação | 300 | 1 | 0 (0.0%) | 79.7 [75.0, 84.0] | 70.7 [64.9, 76.6] | 56.3 [50.7, 62.0] | 54.7 [49.0, 60.3] | 84.3 [80.0, 88.3] | 56.3 [50.7, 62.0] | 64.7 [59.3, 70.0] | 65.7 [60.3, 71.0] | 47.5 (61) | 64.3 (42) |
| E2 BM25 | estimação | 300 | 1 | 0 (0.0%) | 68.7 [63.3, 73.7] | 73.3 [67.0, 79.1] | 50.3 [44.7, 56.0] | 45.3 [40.0, 51.0] | 86.3 [82.3, 90.0] | 50.3 [44.7, 56.0] | 60.3 [55.0, 66.0] | 65.0 [59.7, 70.3] | 54.5 (11) | 14.3 (42) |
| E3 embedding (Bedrock Titan v2) | estimação | 300 | 1 | 0 (0.0%) | 74.0 [69.0, 79.0] | 81.1 [75.7, 86.0] | 60.0 [54.7, 65.7] | 54.7 [49.0, 60.3] | 88.7 [85.0, 92.0] | 60.0 [54.7, 65.7] | 69.3 [64.0, 74.7] | 72.0 [67.0, 77.0] | 72.2 (18) | 31.0 (42) |
| E10 sonda (vetores Bedrock) | estimação | 300 | 1 | 0 (0.0%) | 72.3 [67.0, 77.3] | 81.6 [76.5, 86.6] | 59.0 [53.3, 64.7] | 54.3 [48.7, 60.0] | 82.7 [78.3, 87.0] | 59.0 [53.3, 64.7] | 67.0 [61.7, 72.3] | 69.7 [64.3, 75.0] | 40.0 (50) | 47.6 (42) |
| E11 híbrido regex+sonda | estimação | 300 | 1 | 0 (0.0%) | 80.7 [76.0, 85.3] | 77.3 [71.9, 82.2] | 62.3 [56.7, 67.7] | 60.0 [54.3, 65.7] | 88.3 [84.3, 92.0] | 62.3 [56.7, 67.7] | 73.3 [68.3, 78.3] | 77.3 [72.7, 82.0] | 63.0 (27) | 40.5 (42) |
| E4 Jev | confirmatório (H3-L) | 900 | 3 | 1 (0.1%) | 91.4 [88.3, 94.2] | 92.8 [89.9, 95.5] | 84.9 [81.1, 88.4] | 78.9 [74.3, 83.1] | 97.1 [95.1, 98.7] | 84.9 [81.1, 88.4] | 89.2 [85.9, 92.2] | 90.2 [87.0, 93.1] | 90.6 (127) | 89.7 (126) |
| E6 Haiku 4.5 | confirmatório (H2-L, H3-L) | 300 | 1 | 0 (0.0%) | 92.0 [88.7, 95.0] | 89.1 [85.1, 92.8] | 82.0 [77.7, 86.0] | 78.3 [73.7, 82.7] | 95.0 [92.3, 97.3] | 82.0 [77.7, 86.0] | 88.7 [85.0, 92.0] | 91.3 [88.0, 94.3] | 77.6 (49) | 90.5 (42) |
| E6m Ministral 3 8B | confirmatório (H2-L) | 300 | 1 | 1 (0.3%) | 83.3 [79.0, 87.3] | 95.2 [92.4, 97.6] | 79.3 [74.7, 84.0] | 72.3 [67.0, 77.3] | 92.0 [88.7, 95.0] | 79.3 [74.7, 84.0] | 82.7 [78.3, 87.0] | 83.0 [78.7, 87.3] | 67.9 (56) | 88.1 (42) |
| E6n Nemotron Nano 9B v2 | estimação | 300 | 1 | 11 (3.7%) | 82.0 [77.7, 86.3] | 89.0 [85.0, 92.7] | 73.0 [68.0, 78.0] | 67.7 [62.3, 73.0] | 88.7 [85.0, 92.0] | 73.0 [68.0, 78.0] | 78.3 [73.7, 83.0] | 80.0 [75.3, 84.3] | 69.4 (36) | 59.5 (42) |
| E7-L regex->Jev | estimação | 900 | 3 | 0 (0.0%) | 89.7 [86.2, 92.8] | 92.1 [89.0, 94.9] | 82.6 [78.3, 86.4] | 77.2 [72.6, 81.7] | 96.3 [94.1, 98.2] | 82.6 [78.3, 86.4] | 86.9 [83.1, 90.4] | 88.1 [84.6, 91.4] | 85.2 (135) | 89.7 (126) |
| E9-L regex->Jev->Sonnet | estimação | 900 | 3 | 0 (0.0%) | 89.7 [86.2, 92.8] | 92.2 [89.1, 95.0] | 82.7 [78.6, 86.6] | 77.2 [72.6, 81.7] | 96.4 [94.1, 98.3] | 82.7 [78.6, 86.6] | 87.0 [83.2, 90.6] | 88.1 [84.6, 91.4] | 85.3 (136) | 90.5 (126) |
| E12-L híbrido->Jev->Sonnet (exploratório) | exploratório | 900 | 3 | 0 (0.0%) | 90.1 [86.7, 93.2] | 92.1 [89.0, 94.9] | 83.0 [79.0, 86.9] | 77.4 [72.8, 81.9] | 96.8 [94.7, 98.7] | 83.0 [79.0, 86.9] | 87.9 [84.2, 91.2] | 88.8 [85.2, 92.1] | 87.2 (133) | 90.5 (126) |

### Custo de roteamento por 1 000 casos (US$), três regimes

- **observado**: `cost_usd.routing` como gravado por linha (o regime da co-primária de H1-L): o custo gravado de cada estágio consultado;
- **tabela sem cache**: tokens gravados × preço de tabela (`config/prices.yaml`), sem desconto de cache de prompt; o Jev não tem preço de tabela, então usa-se o custo reportado pelo OpenRouter; roteadores só de CPU = 0;
- **cache modelado**: chegadas Poisson no QPS dado, TTL de 5 minutos renovado a cada acerto, por prefixo de prompt (modelo da fase 1). Modelo, não medição.

| roteador | observado [IC 95%] | tabela sem cache [IC 95%] | modelado @ 0.01 QPS | modelado @ 0.1 QPS | modelado @ 1 QPS | modelado @ 10 QPS | modelado ∞ |
|---|---|---|---|---|---|---|---|
| E1 regex | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E2 BM25 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E3 embedding (Bedrock Titan v2) | 0.002 [0.002, 0.002] | 0.002 [0.002, 0.002] | 0.002 | 0.002 | 0.002 | 0.002 | 0.002 |
| E10 sonda (vetores Bedrock) | 0.002 [0.002, 0.002] | 0.002 [0.002, 0.002] | 0.002 | 0.002 | 0.002 | 0.002 | 0.002 |
| E11 híbrido regex+sonda | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E4 Jev | 0.977 [0.855, 1.109] | 0.977 [0.855, 1.109] (Jev: reportado, sem preço de tabela) | 0.977 | 0.977 | 0.977 | 0.977 | 0.977 |
| E6 Haiku 4.5 | 7.154 [7.067, 7.240] | 7.154 [7.067, 7.240] | 7.154 | 7.154 | 7.154 | 7.154 | 7.154 |
| E6m Ministral 3 8B | 0.694 [0.685, 0.704] | 0.694 [0.685, 0.704] | 0.694 | 0.694 | 0.694 | 0.694 | 0.694 |
| E6n Nemotron Nano 9B v2 | 0.324 [0.320, 0.327] | 0.324 [0.320, 0.327] | 0.324 | 0.324 | 0.324 | 0.324 | 0.324 |
| E7-L regex->Jev | 0.864 [0.747, 0.996] | 0.864 [0.747, 0.996] (Jev: reportado, sem preço de tabela) | 0.864 | 0.864 | 0.864 | 0.864 | 0.864 |
| E9-L regex->Jev->Sonnet | 1.003 [0.859, 1.160] | 1.200 [0.994, 1.424] (Jev: reportado, sem preço de tabela) | 1.251 | 1.221 | 1.077 | 1.004 | 1.003 |
| E12-L híbrido->Jev->Sonnet (exploratório) | 1.054 [0.897, 1.226] | 1.261 [1.042, 1.501] (Jev: reportado, sem preço de tabela) | 1.318 | 1.279 | 1.106 | 1.037 | 1.037 |

## B. Calibração [E] no test_l: Brier / ECE (10 bins de mesma massa), bruto × calibrado no dev

Por decisão tomada (abstenções e linhas de erro fora); nível de tool só nas linhas com skill certa. `raw` = o score do próprio roteador (usage raw_confidence / confidence_raw); `deployed` = a confiança que a run usou (mapa do dev aplicado onde a regra pré-registrada ece_cal < ece_raw o manteve); `dev map` = o mapa ajustado no dev aplicado a toda decisão que tem um, incluindo estágios de LLM em que ele NÃO foi implantado (post hoc, exploratório). Nas cascatas usa-se o score do passo que resolveu.

| roteador | nível | n decisões | Brier / ECE bruto | Brier / ECE implantado | Brier / ECE mapa do dev | mapa usado (decisões) |
|---|---|---|---|---|---|---|
| E1 regex | skill | 280 | 0.152 / 0.115 | 0.137 / 0.107 | 0.137 / 0.107 | implantado 280 |
| E1 regex | tool | 217 | 0.204 / 0.137 | 0.202 / 0.167 | 0.202 / 0.167 | implantado 217 |
| E2 BM25 | skill | 300 | 0.451 / 0.527 | 0.157 / 0.078 | 0.157 / 0.078 | implantado 300 |
| E2 BM25 | tool | 206 | 0.458 / 0.540 | 0.184 / 0.149 | 0.184 / 0.149 | implantado 206 |
| E3 embedding (Bedrock Titan v2) | skill | 300 | 0.152 / 0.068 | 0.152 / 0.068 | 0.152 / 0.068 | nenhum 300 |
| E3 embedding (Bedrock Titan v2) | tool | 222 | 0.145 / 0.112 | 0.149 / 0.102 | 0.149 / 0.102 | implantado 222 |
| E10 sonda (vetores Bedrock) | skill | 300 | 0.159 / 0.057 | 0.159 / 0.057 | 0.159 / 0.057 | nenhum 300 |
| E10 sonda (vetores Bedrock) | tool | 217 | 0.131 / 0.117 | 0.120 / 0.067 | 0.120 / 0.067 | implantado 217 |
| E11 híbrido regex+sonda | skill | 300 | 0.137 / 0.103 | 0.128 / 0.060 | 0.128 / 0.060 | implantado 300 |
| E11 híbrido regex+sonda | tool | 242 | 0.137 / 0.137 | 0.128 / 0.100 | 0.128 / 0.100 | implantado 242 |
| E4 Jev | skill | 899 | 0.076 / 0.049 | 0.073 / 0.051 | 0.073 / 0.051 | implantado 899 |
| E4 Jev | tool | 823 | 0.052 / 0.063 | 0.052 / 0.063 | 0.063 / 0.105 | post hoc 823 |
| E6 Haiku 4.5 | skill | 300 | 0.079 / 0.088 | 0.074 / 0.094 | 0.074 / 0.094 | implantado 300 |
| E6 Haiku 4.5 | tool | 276 | 0.079 / 0.089 | 0.079 / 0.089 | 0.075 / 0.076 | post hoc 276 |
| E6m Ministral 3 8B | skill | 299 | 0.155 / 0.153 | 0.134 / 0.207 | 0.134 / 0.207 | implantado 299 |
| E6m Ministral 3 8B | tool | 250 | 0.048 / 0.068 | 0.070 / 0.185 | 0.070 / 0.185 | implantado 250 |
| E6n Nemotron Nano 9B v2 | skill | 289 | 0.129 / 0.146 | 0.123 / 0.208 | 0.123 / 0.208 | implantado 289 |
| E6n Nemotron Nano 9B v2 | tool | 246 | 0.100 / 0.137 | 0.112 / 0.229 | 0.112 / 0.229 | implantado 246 |
| E7-L regex->Jev | skill | 900 | 0.093 / 0.058 | 0.089 / 0.057 | 0.089 / 0.057 | implantado 900 |
| E7-L regex->Jev | tool | 807 | 0.055 / 0.062 | 0.055 / 0.062 | 0.064 / 0.105 | post hoc 807 |
| E9-L regex->Jev->Sonnet | skill | 900 | 0.093 / 0.058 | 0.089 / 0.057 | 0.089 / 0.057 | implantado 900 |
| E9-L regex->Jev->Sonnet | tool | 807 | 0.053 / 0.073 | 0.053 / 0.074 | 0.064 / 0.113 | post hoc 788, implantado 19 |
| E12-L híbrido->Jev->Sonnet (exploratório) | skill | 900 | 0.085 / 0.080 | 0.080 / 0.058 | 0.080 / 0.058 | implantado 900 |
| E12-L híbrido->Jev->Sonnet (exploratório) | tool | 811 | 0.054 / 0.066 | 0.054 / 0.067 | 0.065 / 0.112 | post hoc 788, implantado 23 |

## C. Predição seletiva [E]: risco × cobertura na conjunta (confiança = min(skill, tool))

| roteador | AURC (menor = melhor) | cobertura % com risco <= 5% | conjunta % com cobertura total |
|---|---|---|---|
| E1 regex | 0.355 | 0.0 | 56.3 |
| E2 BM25 | 0.288 | 2.0 | 50.3 |
| E3 embedding (Bedrock Titan v2) | 0.204 | 14.7 | 60.0 |
| E10 sonda (vetores Bedrock) | 0.204 | 18.3 | 59.0 |
| E11 híbrido regex+sonda | 0.162 | 13.7 | 62.3 |
| E4 Jev | 0.039 | 68.7 | 84.9 |
| E6 Haiku 4.5 | 0.088 | 0.0 | 82.0 |
| E6m Ministral 3 8B | 0.177 | 0.0 | 79.3 |
| E6n Nemotron Nano 9B v2 | 0.227 | 0.0 | 73.0 |
| E7-L regex->Jev | 0.044 | 67.9 | 82.6 |
| E9-L regex->Jev->Sonnet | 0.044 | 67.3 | 82.7 |
| E12-L híbrido->Jev->Sonnet (exploratório) | 0.046 | 64.9 | 83.0 |

## D. Latência p50/p95 [E] (só benchmark dedicado: lat-l-<strategy>-b1..4)

Quente = todo caso menos o primeiro de cada bloco, sem erro; o primeiro caso de um bloco é frio e reportado à parte. IC 95%: bootstrap por cluster sobre os casos.

| estratégia | blocos | n quente | p50 ms [IC 95%] | p95 ms [IC 95%] | frio mediana / máx ms | linhas de erro |
|---|---|---|---|---|---|---|
| regex | 1,2,3,4 | 96 | 1.14 [1.01, 1.28] | 2.04 [1.84, 2.49] | 2 / 4 | 0 |
| bm25 | 1,2,3,4 | 96 | 14 [12, 15] | 28 [24, 32] | 34 / 50 | 0 |
| embedding | 1,2,3,4 | 96 | 146 [141, 150] | 567 [206, 596] | 291 / 23753 | 0 |
| e3c | **NÃO RODADA** |  |  |  |  |  |
| e3t | **NÃO RODADA** |  |  |  |  |  |
| classifier | 1,2,3,4 | 96 | 144 [139, 148] | 280 [258, 355] | 246 / 311 | 0 |
| hybrid | 1,2,3,4 | 96 | 144 [139, 148] | 277 [256, 351] | 246 / 311 | 0 |
| jev | 1,2,3,4 | 95 | 4895 [4537, 5528] | 9193 [7450, 10554] | 5919 / 8145 | 1 |
| haiku | 1,2,3,4 | 96 | 3727 [3637, 3834] | 5278 [4881, 7287] | 3054 / 3297 | 0 |
| e6m | 1,2,3,4 | 96 | 873 [852, 1055] | 1383 [1360, 1410] | 870 / 895 | 0 |
| e6n | 1,2,3,4 | 91 | 1331 [1299, 1359] | 1510 [1482, 1595] | 1540 / 2328 | 5 |
| e7 | 1,2,3,4 | 95 | 3315 [2661, 3992] | 7542 [6735, 8858] | 3266 / 5720 | 1 |
| e9 | 1,2,3,4 | 96 | 3391 [2732, 3894] | 9552 [7659, 12719] | 3876 / 5813 | 0 |

## E. Cobertura da cascata por passo [E]

### Cobertura do regex no limiar congelado (estágio de skill)

| cascata | config | regex min_confidence | parcela resolvida pelo regex % | acurácia de skill ali % |
|---|---|---|---|---|
| E7 | e7_regex_jev_l | 0.88 | 60.0 | 91.1 |
| E9 | e9_regex_jev_llm_l | 0.88 | 60.0 | 91.1 |
| E12 | e12_hybrid_jev_llm_l | - | 0.0 | - |

### Todos os passos (parcela de linhas resolvidas em cada passo e acurácia ali; acurácia de tool dada a skill certa)

| run | estágio | resolvido por | linhas | parcela % | acurácia % |
|---|---|---|---|---|---|
| E7 (l-e7-tuned-routing-r3) | skill | regex | 540 | 60.0 | 91.1 |
| E7 (l-e7-tuned-routing-r3) | skill | jev | 360 | 40.0 | 87.5 |
| E7 (l-e7-tuned-routing-r3) | tool | jev | 900 | 100.0 | 92.1 |
| E9 (l-e9-tuned-routing-r3) | skill | regex | 540 | 60.0 | 91.1 |
| E9 (l-e9-tuned-routing-r3) | skill | jev | 360 | 40.0 | 87.5 |
| E9 (l-e9-tuned-routing-r3) | tool | jev | 870 | 96.7 | 93.1 |
| E9 (l-e9-tuned-routing-r3) | tool | llm | 30 | 3.3 | 52.6 |
| E12 (x-l-e12-hybrid-tuned-routing-r3) | skill | hybrid | 639 | 71.0 | 90.6 |
| E12 (x-l-e12-hybrid-tuned-routing-r3) | skill | jev | 261 | 29.0 | 88.9 |
| E12 (x-l-e12-hybrid-tuned-routing-r3) | tool | jev | 866 | 96.2 | 93.1 |
| E12 (x-l-e12-hybrid-tuned-routing-r3) | tool | llm | 34 | 3.8 | 56.5 |

## F. Decomposição de ponta a ponta (executor Sonnet 5; ITT, % [IC 95%]) [E]

e2e_success = primeira chamada + clarificação + recuperação (disjuntos). Os dois scorers; o simétrico é o primário.

| run | scorer | linhas | erros | skill | e2e_success | = primeira chamada | + clarificação | + recuperação | e2e_strict | args válidos | args_invented (menor = melhor) | entity_grounded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E0-L nativo (sem roteador) | sym (primário) | 300 | 0 | 79.3 [74.7, 83.7] | 57.3 [51.7, 62.7] | 45.7 [40.3, 51.3] | 11.0 [7.7, 14.7] | 0.7 [0.0, 1.7] | 57.0 [51.3, 62.3] | 66.3 [61.0, 71.7] | 0.9 [0.0, 2.3] | 94.6 [91.9, 97.0] |
| E0-L nativo (sem roteador) | legacy (sensibilidade) | 300 | 0 | 87.0 [83.0, 90.7] | 54.7 [49.0, 60.3] | 45.3 [39.7, 51.0] | 8.7 [5.7, 12.0] | 0.7 [0.0, 1.7] | 54.3 [48.7, 60.0] | 64.0 [58.7, 69.3] | 0.9 [0.0, 2.3] | 94.6 [91.9, 97.0] |
| E9-L regex->Jev->Sonnet | sym (primário) | 300 | 0 | 81.7 [77.3, 86.0] | 57.0 [51.3, 62.3] | 45.0 [39.3, 50.7] | 11.3 [8.0, 15.0] | 0.7 [0.0, 1.7] | 57.0 [51.3, 62.3] | 69.3 [64.3, 74.3] | 0.4 [0.0, 1.3] | 95.7 [93.3, 97.7] |
| E9-L regex->Jev->Sonnet | legacy (sensibilidade) | 300 | 0 | 88.0 [84.3, 91.3] | 51.3 [45.7, 57.0] | 41.0 [35.3, 46.7] | 9.7 [6.3, 13.0] | 0.7 [0.0, 1.7] | 51.3 [45.7, 57.0] | 67.7 [62.3, 72.7] | 0.4 [0.0, 1.3] | 95.7 [93.3, 97.7] |
| E9-L todas as tools da skill | sym (primário) | 300 | 0 | 79.7 [75.0, 84.0] | 56.7 [51.0, 62.3] | 44.7 [39.0, 50.3] | 11.3 [7.7, 15.0] | 0.7 [0.0, 1.7] | 56.7 [51.0, 62.3] | 68.7 [63.3, 73.7] | 0.4 [0.0, 1.3] | 95.6 [93.3, 97.7] |
| E9-L todas as tools da skill | legacy (sensibilidade) | 300 | 0 | 88.7 [85.0, 92.0] | 51.7 [46.0, 57.3] | 41.3 [35.7, 47.0] | 9.7 [6.3, 13.3] | 0.7 [0.0, 1.7] | 51.7 [46.0, 57.3] | 67.0 [61.7, 72.3] | 0.4 [0.0, 1.3] | 95.6 [93.3, 97.7] |

### Custo por turno (US$ por 1 000 turnos, observado; tabela = sem desconto de cache de prompt)

| run | total [IC] | roteamento [IC] | executor [IC] | total tabela sem cache [IC] | tokens de prompt do executor/turno [IC] |
|---|---|---|---|---|---|
| E0-L nativo (sem roteador) | 10.16 [9.41, 10.96] | 0.00 [0.00, 0.00] | 10.16 [9.41, 10.96] | 39.95 [38.03, 41.90] | 18254 [17363, 19152] |
| E9-L regex->Jev->Sonnet | 11.19 [10.39, 12.01] | 0.98 [0.85, 1.13] | 10.21 [9.43, 10.99] | 24.46 [23.49, 25.45] | 10067 [9669, 10475] |
| E9-L todas as tools da skill | 8.90 [8.32, 9.49] | 0.98 [0.85, 1.13] | 7.91 [7.36, 8.47] | 29.36 [28.10, 30.61] | 12477 [11916, 13038] |

### Variância do executor (rep 2 em 60 casos; scorer simétrico)

| braço | run | casos | mudança de e2e % [IC] | principal -> rep2 % |
|---|---|---|---|---|
| E0 | l-e0-native-e2e-rep2-60 | 60 | 1.7 [0.0, 5.0] | 58.3 -> 56.7 |
| E9 | l-e9-tuned-e2e-rep2-60 | 60 | 0.0 [0.0, 0.0] | 58.3 -> 58.3 |

## G. Taxas de mudança entre repetições (rep 1 × rep 2, temperatura 0) [E]

| braço | run | casos | mudanças de decisão n (% [IC]) | mudanças de acerto conjunto n (% [IC]) |
|---|---|---|---|---|
| E1 regex (20 casos x 2) | l-e1-regex-routing-repeat20 | 20 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) |
| E6 Haiku 4.5 (60 casos x 2) | l-e6-haiku-canonical-rep2-60 | 60 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) |
| E6m Ministral 3 8B (50 casos x 2) | l-e6m-ministral-canonical-repeat50 | 50 | 1 (2.0 [0.0, 6.0]) | 0 (0.0 [0.0, 0.0]) |
| E6n Nemotron 9B (50 casos x 2) | l-e6n-nemotron-canonical-repeat50 | 50 | 1 (2.0 [0.0, 6.0]) | 1 (2.0 [0.0, 6.0]) |

## H. Taxas de erro e de falha de parse [E] (ESTIMAÇÃO; ITT)

Linha de erro = a linha reescorada carrega um erro (contada como errada no ITT). Falha de parse = uma chamada de estágio cuja saída estruturada falhou na validação (`usage.parse_fail`); o rescore a transforma em linha de erro, embora o log do manifesto tenha contado 0 erros de infra (o mesmo mecanismo das 2 linhas E4 Jev da fase 1). Chamadas de estágio = chamadas dos estágios de skill + tool (2 por linha).

| braço | linhas | linhas de erro n (% [IC 95%]) | tipos | chamadas de estágio | chamadas com falha de parse n (% das chamadas) | chamadas com retentativa do provedor |
|---|---|---|---|---|---|---|
| E1 regex | 300 | 0 (0.0 [0.0, 0.0]) | - | 580 | 0 (0.00%) | 0 |
| E2 BM25 | 300 | 0 (0.0 [0.0, 0.0]) | - | 600 | 0 (0.00%) | 0 |
| E3 embedding (Bedrock Titan v2) | 300 | 0 (0.0 [0.0, 0.0]) | - | 600 | 0 (0.00%) | 0 |
| E10 sonda (vetores Bedrock) | 300 | 0 (0.0 [0.0, 0.0]) | - | 600 | 0 (0.00%) | 0 |
| E11 híbrido regex+sonda | 300 | 0 (0.0 [0.0, 0.0]) | - | 600 | 0 (0.00%) | 0 |
| E4 Jev | 900 | 1 (0.0 [0.0, 0.0]) | jev: parse_fail ×1 | 1799 | 1 (0.06%) | 166 |
| E6 Haiku 4.5 | 300 | 0 (0.0 [0.0, 0.0]) | - | 600 | 0 (0.00%) | 0 |
| E6m Ministral 3 8B | 300 | 1 (0.3 [0.0, 1.0]) | llm: parse_fail ×1 | 600 | 1 (0.17%) | 0 |
| E6n Nemotron Nano 9B v2 | 300 | 11 (3.7 [1.7, 6.0]) | llm: parse_fail ×11 | 599 | 11 (1.84%) | 0 |
| E7-L regex->Jev | 900 | 0 (0.0 [0.0, 0.0]) | - | 2160 | 0 (0.00%) | 137 |
| E9-L regex->Jev->Sonnet | 900 | 0 (0.0 [0.0, 0.0]) | - | 2190 | 0 (0.00%) | 137 |
| E12-L híbrido->Jev->Sonnet (exploratório) | 900 | 0 (0.0 [0.0, 0.0]) | - | 2095 | 1 (0.05%) | 130 |

## I. Recortes (conjunta %, ITT, estimativas pontuais; n por célula no cabeçalho) [E]

### Por categoria

| braço | direto (n=90) | parafrase (n=75) | ambiguo (n=60) | multiturno (n=30) | fora_escopo (n=30) | adversarial (n=15) |
|---|---|---|---|---|---|---|
| E1 | 67.8 | 48.0 | 53.3 | 43.3 | 70.0 | 40.0 |
| E2 | 70.0 | 48.0 | 46.7 | 56.7 | 13.3 | 20.0 |
| E3 | 67.8 | 65.3 | 58.3 | 63.3 | 33.3 | 40.0 |
| E10 | 77.8 | 66.7 | 61.7 | 0.0 | 40.0 | 53.3 |
| E11 | 86.7 | 60.0 | 56.7 | 46.7 | 36.7 | 33.3 |
| E4 | 92.6 | 87.1 | 81.7 | 65.6 | 93.3 | 62.2 |
| E6 | 95.6 | 84.0 | 66.7 | 63.3 | 96.7 | 60.0 |
| E6m | 91.1 | 80.0 | 73.3 | 46.7 | 93.3 | 66.7 |
| E6n | 86.7 | 73.3 | 56.7 | 83.3 | 60.0 | 60.0 |
| E7 | 92.2 | 83.1 | 77.2 | 65.6 | 94.4 | 53.3 |
| E9 | 92.2 | 83.1 | 77.8 | 65.6 | 94.4 | 53.3 |
| E12 | 93.0 | 84.4 | 80.6 | 65.6 | 86.7 | 53.3 |

### Tools originais × novas (orig = toda tool aceitável entre as 18 da fase 1, ou fora de escopo)

| braço | orig 18 tools (n=114) | tools novas (n=186) |
|---|---|---|
| E1 | 50.9 | 59.7 |
| E2 | 26.3 | 65.1 |
| E3 | 43.9 | 69.9 |
| E10 | 46.5 | 66.7 |
| E11 | 48.2 | 71.0 |
| E4 | 77.2 | 89.6 |
| E6 | 77.2 | 84.9 |
| E6m | 78.1 | 80.1 |
| E6n | 65.8 | 77.4 |
| E7 | 75.7 | 86.7 |
| E9 | 76.3 | 86.6 |
| E12 | 75.7 | 87.5 |

### Por skill (primeira skill aceitável)

| braço | __abstain__ (n=38) | __global__ (n=18) | assinaturas (n=19) | assistencia_tecnica (n=21) | cartao_loja_crediario (n=18) | fidelidade_cashback (n=20) | marketplace_vendedores (n=19) | notas_fiscais_cadastro (n=19) | pagamentos_reembolsos (n=35) | pedidos_logistica (n=40) | promocoes_precos (n=25) | trocas_devolucoes (n=28) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | 60.5 | 44.4 | 68.4 | 61.9 | 66.7 | 50.0 | 42.1 | 52.6 | 54.3 | 65.0 | 72.0 | 32.1 |
| E2 | 13.2 | 38.9 | 78.9 | 57.1 | 77.8 | 60.0 | 42.1 | 78.9 | 45.7 | 42.5 | 84.0 | 32.1 |
| E3 | 28.9 | 55.6 | 68.4 | 76.2 | 77.8 | 70.0 | 63.2 | 78.9 | 60.0 | 55.0 | 72.0 | 50.0 |
| E10 | 36.8 | 55.6 | 52.6 | 57.1 | 72.2 | 55.0 | 57.9 | 78.9 | 65.7 | 55.0 | 88.0 | 50.0 |
| E11 | 31.6 | 50.0 | 84.2 | 61.9 | 77.8 | 70.0 | 63.2 | 78.9 | 62.9 | 70.0 | 80.0 | 42.9 |
| E4 | 80.7 | 59.3 | 91.2 | 93.7 | 88.9 | 90.0 | 100.0 | 87.7 | 88.6 | 83.3 | 98.7 | 63.1 |
| E6 | 86.8 | 72.2 | 94.7 | 95.2 | 100.0 | 85.0 | 94.7 | 84.2 | 74.3 | 72.5 | 88.0 | 57.1 |
| E6m | 89.5 | 72.2 | 73.7 | 100.0 | 83.3 | 70.0 | 89.5 | 68.4 | 71.4 | 77.5 | 92.0 | 64.3 |
| E6n | 57.9 | 66.7 | 84.2 | 90.5 | 88.9 | 80.0 | 89.5 | 84.2 | 65.7 | 70.0 | 72.0 | 57.1 |
| E7 | 79.8 | 55.6 | 96.5 | 87.3 | 92.6 | 85.0 | 100.0 | 87.7 | 82.9 | 81.7 | 86.7 | 64.3 |
| E9 | 79.8 | 55.6 | 96.5 | 87.3 | 92.6 | 85.0 | 100.0 | 87.7 | 83.8 | 81.7 | 86.7 | 64.3 |
| E12 | 73.7 | 59.3 | 96.5 | 87.3 | 88.9 | 85.0 | 94.7 | 87.7 | 86.7 | 81.7 | 94.7 | 69.0 |

### Por grupo confundível (casos ambiguo; G1-G12 = grupos do perfil grande, P1 = grupos da fase 1)

| braço | G1 (n=4) | G2 (n=4) | G3 (n=4) | G4 (n=4) | G5 (n=4) | G6 (n=4) | G7 (n=4) | G8 (n=4) | G9 (n=4) | G10 (n=3) | G11 (n=2) | G12 (n=3) | P1 (n=14) | outro (n=2) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | 25.0 | 100.0 | 25.0 | 50.0 | 75.0 | 75.0 | 25.0 | 75.0 | 75.0 | 0.0 | 100.0 | 33.3 | 42.9 | 100.0 |
| E2 | 75.0 | 75.0 | 0.0 | 50.0 | 75.0 | 25.0 | 0.0 | 75.0 | 75.0 | 66.7 | 100.0 | 100.0 | 7.1 | 100.0 |
| E3 | 100.0 | 75.0 | 0.0 | 0.0 | 75.0 | 50.0 | 25.0 | 100.0 | 50.0 | 33.3 | 100.0 | 100.0 | 57.1 | 100.0 |
| E10 | 100.0 | 75.0 | 0.0 | 50.0 | 50.0 | 50.0 | 50.0 | 75.0 | 75.0 | 66.7 | 100.0 | 100.0 | 50.0 | 100.0 |
| E11 | 25.0 | 100.0 | 25.0 | 50.0 | 75.0 | 75.0 | 25.0 | 75.0 | 50.0 | 33.3 | 100.0 | 100.0 | 42.9 | 100.0 |
| E4 | 91.7 | 75.0 | 91.7 | 75.0 | 75.0 | 91.7 | 75.0 | 50.0 | 100.0 | 22.2 | 100.0 | 100.0 | 88.1 | 100.0 |
| E6 | 50.0 | 50.0 | 75.0 | 50.0 | 100.0 | 100.0 | 100.0 | 0.0 | 100.0 | 0.0 | 50.0 | 66.7 | 71.4 | 100.0 |
| E6m | 50.0 | 50.0 | 75.0 | 50.0 | 50.0 | 75.0 | 100.0 | 100.0 | 100.0 | 66.7 | 50.0 | 100.0 | 78.6 | 50.0 |
| E6n | 100.0 | 50.0 | 25.0 | 50.0 | 50.0 | 50.0 | 50.0 | 75.0 | 100.0 | 0.0 | 50.0 | 33.3 | 57.1 | 100.0 |
| E7 | 91.7 | 75.0 | 58.3 | 75.0 | 75.0 | 91.7 | 75.0 | 50.0 | 75.0 | 33.3 | 100.0 | 100.0 | 83.3 | 100.0 |
| E9 | 91.7 | 75.0 | 58.3 | 75.0 | 75.0 | 91.7 | 75.0 | 50.0 | 75.0 | 33.3 | 83.3 | 100.0 | 88.1 | 100.0 |
| E12 | 91.7 | 75.0 | 83.3 | 75.0 | 75.0 | 91.7 | 58.3 | 50.0 | 66.7 | 66.7 | 83.3 | 100.0 | 92.9 | 100.0 |
