# Tabelas de estimação: test-v2 (prereg-v1 "somente estimação"; itens exploratórios rotulados)

Gerado por `scripts/analysis/final_all.py`. Intenção de tratar (ITT); ICs de 95% = cluster bootstrap sobre os ids de caso (10k, seed 20260930). Sem testes aqui (descritivo). Runs incluídas apenas quando o arquivo re-pontuado existe e o log do manifest indica COMPLETE.

Runs (ainda) não concluídas e, portanto, ausentes: nenhuma.

## A. Por estratégia (routing-only, ITT; % com IC de 95% por cluster bootstrap)

| router | status | linhas | reps | linhas com erro | skill % | tool % dada skill correta | joint % (métrica primária) | joint first-label % (estrito) | abstain_correct % | recall@1 | recall@2 | recall@3 | precisão de abstenção % (n abstidos) | recall de abstenção % (n esperados) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 regex | estimação | 349 | 1 | 0 (0.0%) | 75.6 [71.1, 79.9] | 69.7 [64.0, 75.0] | 52.7 [47.3, 57.9] | 48.4 [43.3, 53.6] | 79.1 [74.8, 83.4] | 52.7 [47.3, 57.9] | 57.6 [52.4, 62.8] | 57.6 [52.4, 62.8] | 43.4 (99) | 69.1 (55) |
| E2 BM25 | estimação | 349 | 1 | 0 (0.0%) | 71.9 [67.0, 76.5] | 68.1 [62.5, 73.7] | 49.0 [43.8, 54.2] | 46.1 [41.0, 51.3] | 86.0 [82.2, 89.4] | 49.0 [43.8, 54.2] | 59.0 [53.9, 64.2] | 65.6 [60.7, 70.5] | 58.5 (41) | 41.8 (55) |
| E3 embedding (qwen3-emb 8B) | estimação | 349 | 1 | 0 (0.0%) | 85.1 [81.4, 88.8] | 86.5 [82.5, 90.2] | 73.6 [68.8, 78.2] | 67.0 [61.9, 71.9] | 95.1 [92.8, 97.4] | 73.6 [68.8, 78.2] | 83.4 [79.4, 87.1] | 84.8 [81.1, 88.5] | 100.0 (40) | 69.1 (55) |
| E3 ablação qwen3-emb 0.6B | estimação | 349 | 1 | 0 (0.0%) | 78.5 [74.2, 82.8] | 82.1 [77.4, 86.5] | 64.5 [59.3, 69.3] | 57.9 [52.7, 63.0] | 92.0 [89.1, 94.8] | 64.5 [59.3, 69.3] | 75.6 [71.1, 79.9] | 77.9 [73.6, 82.2] | 77.4 (53) | 70.9 (55) |
| E3 ablação bge-m3 | estimação | 349 | 1 | 0 (0.0%) | 78.5 [74.2, 82.8] | 82.1 [77.4, 86.5] | 64.5 [59.3, 69.6] | 59.6 [54.4, 64.8] | 91.7 [88.5, 94.6] | 64.5 [59.3, 69.6] | 73.1 [68.5, 77.7] | 77.1 [72.8, 81.4] | 82.9 (41) | 60.0 (55) |
| E10 classificador (probe) | estimação | 349 | 1 | 0 (0.0%) | 87.1 [83.4, 90.5] | 85.9 [81.9, 89.5] | 74.8 [70.2, 79.4] | 67.9 [63.0, 72.8] | 92.0 [88.8, 94.6] | 74.8 [70.2, 79.4] | 82.2 [78.2, 86.2] | 84.8 [80.8, 88.5] | 74.6 (63) | 78.2 (55) |
| E11 híbrido regex+classificador | estimação | 349 | 1 | 0 (0.0%) | 86.0 [82.2, 89.7] | 84.7 [80.3, 88.7] | 72.8 [67.9, 77.4] | 65.0 [59.9, 69.9] | 94.0 [91.4, 96.3] | 72.8 [67.9, 77.4] | 82.2 [78.2, 86.2] | 84.2 [80.2, 88.0] | 89.6 (48) | 70.9 (55) |
| E6b Qwen3-8B local | estimação | 349 | 1 | 0 (0.0%) | 87.1 [83.7, 90.5] | 91.8 [88.5, 94.7] | 79.9 [75.6, 84.0] | 70.8 [65.9, 75.4] | 97.1 [95.4, 98.9] | 79.9 [75.6, 84.0] | 85.7 [81.9, 89.1] | 86.5 [82.8, 90.0] | 94.5 (55) | 87.3 (55) |
| E4 Jev | estimação | 1047 | 3 | 2 (0.2%) | 92.6 [89.9, 95.2] | 91.4 [88.5, 94.1] | 84.7 [81.0, 88.2] | 75.9 [71.5, 80.1] | 97.1 [95.3, 98.7] | 84.7 [81.0, 88.2] | 90.2 [87.0, 93.1] | 91.0 [88.1, 93.9] | 94.0 (167) | 89.1 (165) |
| E5 Sonnet 5 | confirmatório | 1047 | 3 | 0 (0.0%) | 92.6 [89.7, 95.1] | 90.9 [87.8, 93.8] | 84.1 [80.3, 87.8] | 75.6 [71.2, 79.9] | 97.3 [95.6, 98.9] | 84.1 [80.3, 87.8] | 91.3 [88.3, 94.1] | 92.5 [89.6, 95.0] | 96.7 (152) | 86.1 (165) |
| E6 Haiku 4.5 | estimação | 349 | 1 | 0 (0.0%) | 91.7 [88.5, 94.6] | 92.2 [89.1, 95.0] | 84.5 [80.5, 88.3] | 74.8 [70.2, 79.4] | 96.3 [94.3, 98.0] | 84.5 [80.5, 88.3] | 89.7 [86.5, 92.8] | 91.4 [88.3, 94.3] | 89.8 (59) | 87.3 (55) |
| E7 regex->Jev | confirmatório | 1047 | 3 | 0 (0.0%) | 87.8 [84.2, 91.1] | 91.1 [88.1, 93.9] | 79.9 [75.8, 84.0] | 71.8 [67.2, 76.4] | 95.9 [93.8, 97.7] | 79.9 [75.8, 84.0] | 85.3 [81.6, 88.8] | 86.0 [82.3, 89.5] | 86.3 (182) | 89.1 (165) |
| E8 regex->Sonnet | estimação | 1047 | 3 | 0 (0.0%) | 89.8 [86.5, 92.8] | 90.7 [87.6, 93.7] | 81.5 [77.5, 85.3] | 73.4 [68.9, 77.8] | 96.1 [94.0, 97.9] | 81.5 [77.5, 85.3] | 88.3 [84.8, 91.5] | 89.4 [86.2, 92.6] | 89.1 (165) | 86.1 (165) |
| E9 regex->Jev->Sonnet | confirmatório | 1047 | 3 | 0 (0.0%) | 89.0 [85.7, 92.2] | 91.8 [89.0, 94.5] | 81.8 [77.8, 85.6] | 74.2 [69.7, 78.6] | 96.7 [94.7, 98.3] | 81.8 [77.8, 85.6] | 86.9 [83.4, 90.3] | 88.1 [84.7, 91.3] | 89.9 (168) | 89.1 (165) |
| E12 hybrid->Jev->Sonnet (exploratório) | exploratório | 1047 | 3 | 0 (0.0%) | 90.0 [86.8, 92.8] | 92.3 [89.4, 94.8] | 83.0 [79.1, 86.7] | 74.9 [70.4, 79.3] | 97.5 [95.9, 98.9] | 83.0 [79.1, 86.7] | 88.2 [84.7, 91.4] | 89.2 [85.9, 92.4] | 95.0 (159) | 89.1 (165) |
| E4 Jev P0+P6c (exploratório) | exploratório | 349 | 1 | 1 (0.3%) | 92.3 [89.4, 95.1] | 91.3 [88.2, 94.1] | 84.2 [80.2, 88.0] | 75.1 [70.5, 79.4] | 97.1 [95.4, 98.9] | 84.2 [80.2, 88.0] | 89.7 [86.5, 92.8] | 91.4 [88.3, 94.3] | 94.5 (55) | 89.1 (55) |

### Custo de routing por 1 000 casos (US$), três regimes

- **observed**: o custo registrado de cada decisão consultada, com o prompt cache do provedor no estado em que estava quando a decisão foi computada pela primeira vez (cache quente: as runs compartilham as amostras do shadow pass; independente do response cache) — o regime pré-registrado do co-primário H1;
- **list uncached**: tokens registrados x preço de tabela, sem desconto de prompt cache (config/prices.yaml; Jev não tem preço de tabela, usa-se o custo reportado pela OpenRouter; local = 0);
- **modelled cache**: chegadas de Poisson no QPS indicado, TTL de 5 minutos renovado a cada hit, por prefixo de prompt (modelo, nível, prompt estático); probabilidade de hit 1 - exp(-QPS x share x 300 s); prefixo cacheável = o maior cache read+write já observado para aquele prefixo (prompts do Haiku nunca entram em cache: abaixo do mínimo do provedor). `∞` = toda chamada é um cache hit. Modelo, não medição.

| router | observed [IC 95%] | list uncached [IC 95%] | modelled @ 0.01 QPS | modelled @ 0.1 QPS | modelled @ 1 QPS | modelled @ 10 QPS | modelled ∞ |
|---|---|---|---|---|---|---|---|
| E1 regex | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E2 BM25 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E3 embedding (qwen3-emb 8B) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E3 ablação qwen3-emb 0.6B | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E3 ablação bge-m3 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E10 classificador (probe) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E11 híbrido regex+classificador | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E6b Qwen3-8B local | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E4 Jev | 0.818 [0.739, 0.900] | 0.818 [0.739, 0.900] (Jev: reportado, sem preço de tabela) | 0.818 | 0.818 | 0.818 | 0.818 | 0.818 |
| E5 Sonnet 5 | 4.981 [4.909, 5.052] | 11.820 [11.663, 11.975] | 7.694 | 4.951 | 4.947 | 4.947 | 4.947 |
| E6 Haiku 4.5 | 5.228 [5.154, 5.299] | 5.228 [5.154, 5.299] | 5.228 | 5.228 | 5.228 | 5.228 | 5.228 |
| E7 regex->Jev | 0.727 [0.654, 0.805] | 0.727 [0.654, 0.805] (Jev: reportado, sem preço de tabela) | 0.727 | 0.727 | 0.727 | 0.727 | 0.727 |
| E8 regex->Sonnet | 4.351 [4.258, 4.448] | 10.107 [9.878, 10.338] | 7.242 | 4.319 | 4.315 | 4.315 | 4.315 |
| E9 regex->Jev->Sonnet | 0.989 [0.868, 1.116] | 1.351 [1.134, 1.589] (Jev: reportado, sem preço de tabela) | 1.391 | 1.164 | 0.999 | 0.986 | 0.986 |
| E12 hybrid->Jev->Sonnet (exploratório) | 0.841 [0.730, 0.959] | 1.094 [0.903, 1.302] (Jev: reportado, sem preço de tabela) | 1.146 | 1.026 | 0.849 | 0.835 | 0.835 |
| E4 Jev P0+P6c (exploratório) | 0.611 [0.533, 0.692] | 0.611 [0.533, 0.692] (Jev: reportado, sem preço de tabela) | 0.611 | 0.611 | 0.611 | 0.611 | 0.611 |

## B. Calibração no test-v2: Brier / ECE (10 bins de massa igual), bruto vs calibrado em dev

Por decisão tomada (abstenções e linhas com erro excluídas); nível de tool apenas em linhas com skill correta. `raw` = o score próprio do router (usage raw_confidence / confidence_raw); `deployed` = a confiança que a run usou (mapa de dev aplicado onde a regra pré-registrada ece_cal < ece_raw o manteve); `dev map` = o mapa ajustado em dev aplicado a toda decisão que tenha um, incluindo estágios de LLM onde ele NÃO foi implantado (post hoc, exploratório). Para cascades, usa-se o score da etapa que resolveu.

| router | nível | n decisões | raw Brier / ECE | deployed Brier / ECE | dev map Brier / ECE | mapa usado (decisões) |
|---|---|---|---|---|---|---|
| E1 regex | skill | 322 | 0.214 / 0.184 | 0.182 / 0.179 | 0.182 / 0.179 | implantado 322 |
| E1 regex | tool | 210 | 0.191 / 0.190 | 0.163 / 0.182 | 0.163 / 0.182 | implantado 210 |
| E2 BM25 | skill | 349 | 0.394 / 0.469 | 0.169 / 0.058 | 0.169 / 0.058 | implantado 349 |
| E2 BM25 | tool | 251 | 0.340 / 0.397 | 0.203 / 0.138 | 0.203 / 0.138 | implantado 251 |
| E3 embedding (qwen3-emb 8B) | skill | 349 | 0.118 / 0.060 | 0.114 / 0.063 | 0.114 / 0.063 | implantado 349 |
| E3 embedding (qwen3-emb 8B) | tool | 297 | 0.092 / 0.040 | 0.098 / 0.070 | 0.098 / 0.070 | implantado 297 |
| E3 ablação qwen3-emb 0.6B | skill | 349 | 0.154 / 0.064 | 0.151 / 0.040 | 0.151 / 0.040 | implantado 349 |
| E3 ablação qwen3-emb 0.6B | tool | 274 | 0.122 / 0.038 | 0.160 / 0.199 | 0.160 / 0.199 | implantado 274 |
| E3 ablação bge-m3 | skill | 349 | 0.163 / 0.061 | 0.158 / 0.057 | 0.158 / 0.057 | implantado 349 |
| E3 ablação bge-m3 | tool | 274 | 0.129 / 0.054 | 0.141 / 0.111 | 0.141 / 0.111 | implantado 274 |
| E10 classificador (probe) | skill | 349 | 0.184 / 0.292 | 0.096 / 0.051 | 0.096 / 0.051 | implantado 349 |
| E10 classificador (probe) | tool | 304 | 0.310 / 0.451 | 0.107 / 0.095 | 0.107 / 0.095 | implantado 304 |
| E11 híbrido regex+classificador | skill | 349 | 0.132 / 0.121 | 0.116 / 0.068 | 0.116 / 0.068 | implantado 349 |
| E11 híbrido regex+classificador | tool | 300 | 0.156 / 0.191 | 0.123 / 0.089 | 0.123 / 0.089 | implantado 300 |
| E6b Qwen3-8B local | skill | 349 | 0.116 / 0.155 | 0.113 / 0.190 | 0.113 / 0.190 | implantado 349 |
| E6b Qwen3-8B local | tool | 304 | 0.079 / 0.105 | 0.083 / 0.198 | 0.083 / 0.198 | implantado 304 |
| E4 Jev | skill | 1045 | 0.072 / 0.048 | 0.067 / 0.036 | 0.067 / 0.036 | implantado 1045 |
| E4 Jev | tool | 970 | 0.073 / 0.065 | 0.073 / 0.065 | 0.084 / 0.117 | post-hoc 970 |
| E5 Sonnet 5 | skill | 1047 | 0.094 / 0.096 | 0.069 / 0.045 | 0.069 / 0.045 | implantado 1047 |
| E5 Sonnet 5 | tool | 969 | 0.083 / 0.097 | 0.083 / 0.097 | 0.082 / 0.103 | post-hoc 969 |
| E6 Haiku 4.5 | skill | 349 | 0.073 / 0.072 | 0.073 / 0.072 | 0.073 / 0.069 | post-hoc 349 |
| E6 Haiku 4.5 | tool | 320 | 0.065 / 0.074 | 0.065 / 0.074 | 0.069 / 0.084 | post-hoc 320 |
| E7 regex->Jev | skill | 1047 | 0.103 / 0.048 | 0.111 / 0.091 | 0.111 / 0.091 | implantado 1047 |
| E7 regex->Jev | tool | 919 | 0.074 / 0.061 | 0.074 / 0.061 | 0.085 / 0.111 | post-hoc 919 |
| E8 regex->Sonnet | skill | 1047 | 0.113 / 0.113 | 0.096 / 0.079 | 0.096 / 0.079 | implantado 1047 |
| E8 regex->Sonnet | tool | 940 | 0.084 / 0.096 | 0.084 / 0.096 | 0.083 / 0.099 | post-hoc 940 |
| E9 regex->Jev->Sonnet | skill | 1047 | 0.099 / 0.063 | 0.099 / 0.073 | 0.099 / 0.073 | implantado 1047 |
| E9 regex->Jev->Sonnet | tool | 932 | 0.073 / 0.062 | 0.073 / 0.062 | 0.084 / 0.114 | post-hoc 932 |
| E12 hybrid->Jev->Sonnet (exploratório) | skill | 1047 | 0.109 / 0.104 | 0.090 / 0.060 | 0.090 / 0.060 | implantado 1047 |
| E12 hybrid->Jev->Sonnet (exploratório) | tool | 942 | 0.072 / 0.066 | 0.072 / 0.066 | 0.083 / 0.118 | post-hoc 942 |
| E4 Jev P0+P6c (exploratório) | skill | 348 | 0.074 / 0.050 | 0.069 / 0.039 | 0.069 / 0.039 | implantado 348 |
| E4 Jev P0+P6c (exploratório) | tool | 322 | 0.087 / 0.078 | 0.087 / 0.078 | 0.092 / 0.125 | post-hoc 322 |

## C. Predição seletiva: risco-cobertura no joint (confiança = min(skill, tool))

| router | AURC (menor = melhor) | cobertura % com risco <= 5% | joint % com cobertura total |
|---|---|---|---|
| E1 regex | 0.372 | 0.0 | 52.7 |
| E2 BM25 | 0.317 | 7.7 | 49.0 |
| E3 embedding (qwen3-emb 8B) | 0.109 | 40.4 | 73.6 |
| E3 ablação qwen3-emb 0.6B | 0.175 | 5.7 | 64.5 |
| E3 ablação bge-m3 | 0.190 | 17.8 | 64.5 |
| E10 classificador (probe) | 0.097 | 17.5 | 74.8 |
| E11 híbrido regex+classificador | 0.135 | 23.5 | 72.8 |
| E6b Qwen3-8B local | 0.181 | 11.5 | 79.9 |
| E4 Jev | 0.055 | 55.9 | 84.7 |
| E5 Sonnet 5 | 0.050 | 61.5 | 84.1 |
| E6 Haiku 4.5 | 0.068 | 51.3 | 84.5 |
| E7 regex->Jev | 0.079 | 40.7 | 79.9 |
| E8 regex->Sonnet | 0.062 | 59.6 | 81.5 |
| E9 regex->Jev->Sonnet | 0.072 | 42.1 | 81.8 |
| E12 hybrid->Jev->Sonnet (exploratório) | 0.067 | 47.8 | 83.0 |
| E4 Jev P0+P6c (exploratório) | 0.061 | 46.7 | 84.2 |

## D. Latência (benchmark dedicado lat-*, ÚNICA fonte de números de latência)

100 casos estratificados do test-v2 em 4 blocos de 25, intercalação das 12 estratégias no nível de bloco, concorrência 1, response cache desligado e vector cache novo. Latência de routing (estágio de skill + tool) por caso. O primeiro caso de cada bloco é **cold** (reportado à parte: mediana / máximo sobre os 4 blocos); os 96 restantes são **warm**. ICs de 95%: cluster bootstrap sobre os casos. O p99 de 96 valores fica próximo do máximo amostral: leia-o como indicador de cauda. API = chamada de rede para Bedrock / OpenRouter (inclui enfileiramento no provedor); local = esta máquina (Apple Silicon, Ollama para qwen/embedding).

| estratégia | onde | blocos | n warm | p50 ms [IC 95%] | p95 ms [IC 95%] | p99 ms [IC 95%] | primeiro caso cold ms mediana / máx | linhas com erro |
|---|---|---|---|---|---|---|---|---|
| regex | local | 4 | 96 | 0.15 [0.14, 0.17] | 0.36 [0.26, 0.50] | 0.58 [0.36, 0.86] | 0.14 / 0.22 | 0 |
| bm25 | local | 4 | 96 | 2.62 [2.26, 3.15] | 7.25 [5.64, 8.20] | 10 [7, 13] | 5.90 / 6.66 | 0 |
| embedding | local | 4 | 96 | 427 [419, 436] | 710 [574, 1492] | 1514 [702, 1559] | 493 / 8921 | 0 |
| classifier | local | 4 | 96 | 419 [413, 425] | 1048 [635, 4634] | 5093 [1178, 5490] | 465 / 509 | 0 |
| hybrid | local | 4 | 96 | 419 [414, 428] | 1037 [634, 4624] | 5088 [1167, 5477] | 465 / 509 | 0 |
| qwen | local | 4 | 96 | 9875 [8726, 9960] | 11983 [10394, 12264] | 12366 [11988, 12559] | 6675 / 10012 | 0 |
| jev | API | 4 | 96 | 4308 [4066, 4576] | 6851 [6303, 7531] | 7789 [6835, 11560] | 3015 / 5718 | 0 |
| sonnet | API | 4 | 96 | 6287 [6140, 6580] | 10994 [9333, 13065] | 13226 [11021, 13320] | 5592 / 9149 | 0 |
| haiku | API | 4 | 96 | 3507 [3421, 3648] | 5919 [5027, 6861] | 7668 [5923, 7900] | 2903 / 3359 | 0 |
| e7 | API | 4 | 96 | 3431 [3094, 3842] | 7129 [5785, 8470] | 10719 [7105, 11212] | 2777 / 5475 | 0 |
| e8 | API | 4 | 95 | 5059 [4313, 5760] | 7956 [7149, 14653] | 17007 [8159, 18192] | 5428 / 5811 | 1 |
| e9 | API | 4 | 96 | 3662 [3349, 4212] | 9892 [6903, 11874] | 12439 [9749, 12728] | 2302 / 6282 | 0 |

## E. Desagregações (descritivo; sem testes)

### Joint % por categoria [IC 95%]

| router | direto (n=105) | parafrase (n=87) | ambiguo (n=70) | multiturno (n=35) | fora_escopo (n=35) | adversarial (n=17) |
|---|---|---|---|---|---|---|
| E1 regex | 75.2 [66.7, 82.9] | 31.0 [21.8, 41.4] | 44.3 [32.9, 55.7] | 54.3 [37.1, 71.4] | 60.0 [42.9, 74.3] | 41.2 [17.6, 64.7] |
| E2 BM25 | 68.6 [60.0, 77.1] | 47.1 [36.8, 57.5] | 31.4 [21.4, 42.9] | 48.6 [31.4, 65.7] | 31.4 [17.1, 45.7] | 47.1 [23.5, 70.6] |
| E3 embedding (qwen3-emb 8B) | 81.0 [73.3, 88.6] | 80.5 [72.4, 88.5] | 67.1 [55.7, 78.6] | 68.6 [51.4, 82.9] | 68.6 [51.4, 82.9] | 41.2 [17.6, 64.7] |
| E10 classificador (probe) | 87.6 [81.0, 93.3] | 79.3 [70.1, 87.4] | 71.4 [60.0, 81.4] | 34.3 [20.0, 51.4] | 80.0 [65.7, 91.4] | 58.8 [35.3, 82.4] |
| E11 híbrido regex+classificador | 86.7 [80.0, 92.4] | 71.3 [62.1, 80.5] | 70.0 [58.6, 80.0] | 54.3 [37.1, 71.4] | 71.4 [57.1, 85.7] | 47.1 [23.5, 70.6] |
| E6b Qwen3-8B local | 87.6 [81.0, 93.3] | 77.0 [67.8, 85.1] | 75.7 [65.7, 85.7] | 80.0 [65.7, 91.4] | 82.9 [68.6, 94.3] | 58.8 [35.3, 82.4] |
| E4 Jev | 91.1 [85.4, 96.2] | 81.2 [72.8, 88.5] | 75.7 [66.2, 84.8] | 89.5 [80.0, 97.1] | 91.4 [80.0, 100.0] | 76.5 [52.9, 94.1] |
| E5 Sonnet 5 | 89.5 [83.2, 94.9] | 83.1 [75.1, 90.8] | 77.1 [67.6, 86.2] | 85.7 [74.3, 97.1] | 91.4 [80.0, 100.0] | 66.7 [43.1, 88.2] |
| E6 Haiku 4.5 | 88.6 [81.9, 94.3] | 82.8 [74.7, 89.7] | 78.6 [68.6, 87.1] | 85.7 [74.3, 97.1] | 88.6 [77.1, 97.1] | 82.4 [64.7, 100.0] |
| E7 regex->Jev | 90.2 [84.1, 95.2] | 76.2 [67.4, 84.7] | 72.9 [62.9, 82.4] | 85.7 [74.3, 96.2] | 74.3 [60.0, 88.6] | 64.7 [41.2, 88.2] |
| E8 regex->Sonnet | 90.8 [85.1, 95.6] | 78.2 [69.0, 86.2] | 75.2 [65.2, 84.8] | 82.9 [68.6, 94.3] | 82.9 [68.6, 94.3] | 60.8 [37.3, 82.4] |
| E9 regex->Jev->Sonnet | 91.1 [85.4, 95.9] | 76.2 [67.4, 84.3] | 74.8 [64.8, 83.8] | 85.7 [74.3, 96.2] | 82.9 [68.6, 94.3] | 70.6 [47.1, 88.2] |

os rótulos de ambiguo são fracos (o auditor A aceitou 23/70 conjuntos de rótulos ambíguos do test-v2): a coluna ambiguo é reportada à parte de propósito.

### Joint % por tool gold (a primeira listada), estimativas pontuais

| tool gold | n casos | E1 | E2 | E3 | E10 | E11 | E6b | E4 | E5 | E6 | E7 | E8 | E9 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| __abstain__ | 42 | 50 | 29 | 60 | 71 | 62 | 74 | 86 | 82 | 83 | 67 | 72 | 76 |
| get_order_status | 28 | 50 | 29 | 50 | 57 | 71 | 82 | 80 | 70 | 71 | 80 | 70 | 76 |
| create_return_request | 26 | 54 | 35 | 88 | 69 | 69 | 81 | 82 | 85 | 81 | 74 | 79 | 77 |
| cancel_order | 24 | 58 | 50 | 75 | 79 | 83 | 92 | 89 | 90 | 79 | 85 | 82 | 86 |
| get_payment_status | 22 | 59 | 32 | 86 | 82 | 73 | 73 | 94 | 88 | 91 | 89 | 88 | 91 |
| search_help_center | 22 | 23 | 23 | 9 | 41 | 32 | 32 | 53 | 59 | 64 | 50 | 55 | 48 |
| dispute_charge | 20 | 55 | 80 | 85 | 70 | 70 | 85 | 75 | 77 | 75 | 75 | 80 | 80 |
| request_refund | 18 | 50 | 28 | 67 | 56 | 61 | 78 | 59 | 69 | 67 | 59 | 74 | 65 |
| track_shipment | 15 | 47 | 47 | 100 | 100 | 93 | 80 | 76 | 93 | 93 | 76 | 93 | 76 |
| create_exchange | 14 | 50 | 57 | 71 | 93 | 86 | 100 | 100 | 93 | 93 | 100 | 93 | 98 |
| get_customer_profile | 14 | 43 | 71 | 79 | 93 | 93 | 86 | 100 | 100 | 100 | 93 | 100 | 100 |
| check_return_eligibility | 13 | 38 | 54 | 54 | 46 | 54 | 69 | 79 | 69 | 77 | 79 | 72 | 79 |
| escalate_to_human | 13 | 38 | 77 | 69 | 100 | 92 | 62 | 100 | 100 | 100 | 92 | 92 | 92 |
| generate_boleto_second_copy | 13 | 100 | 85 | 100 | 85 | 92 | 92 | 100 | 100 | 92 | 100 | 100 | 100 |
| generate_return_label | 13 | 46 | 85 | 92 | 85 | 77 | 85 | 92 | 100 | 100 | 92 | 100 | 92 |
| get_refund_status | 13 | 23 | 31 | 85 | 69 | 23 | 92 | 100 | 100 | 100 | 85 | 85 | 85 |
| open_warranty_claim | 13 | 92 | 46 | 100 | 85 | 100 | 92 | 77 | 62 | 85 | 77 | 62 | 74 |
| reschedule_delivery | 13 | 62 | 85 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| update_delivery_address | 13 | 85 | 92 | 100 | 92 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

### Gold single- vs multi-label (256 casos single-label, 93 multi-label)

| router | single: joint % | single: first-label % | multi: joint % (qualquer rótulo) | multi: first-label % (estrito) |
|---|---|---|---|---|
| E1 regex | 56.6 [50.8, 62.5] | 56.6 [50.8, 62.5] | 41.9 [32.3, 51.6] | 25.8 [17.2, 34.4] |
| E2 BM25 | 53.9 [47.7, 59.8] | 53.9 [47.7, 59.8] | 35.5 [25.8, 45.2] | 24.7 [16.1, 33.3] |
| E3 embedding (qwen3-emb 8B) | 77.0 [71.9, 82.0] | 77.0 [71.9, 82.0] | 64.5 [54.8, 74.2] | 39.8 [30.1, 49.5] |
| E10 classificador (probe) | 76.2 [70.7, 81.2] | 76.2 [70.7, 81.2] | 71.0 [61.3, 79.6] | 45.2 [34.4, 54.8] |
| E11 híbrido regex+classificador | 74.6 [69.1, 80.1] | 74.6 [69.1, 80.1] | 67.7 [58.1, 77.4] | 38.7 [29.0, 48.4] |
| E6b Qwen3-8B local | 82.0 [77.3, 86.7] | 82.0 [77.3, 86.7] | 74.2 [64.5, 82.8] | 39.8 [30.1, 49.5] |
| E4 Jev | 86.6 [82.4, 90.5] | 86.6 [82.4, 90.5] | 79.6 [71.7, 87.1] | 46.6 [36.6, 56.6] |
| E5 Sonnet 5 | 86.5 [82.2, 90.4] | 86.5 [82.2, 90.4] | 77.8 [69.2, 85.7] | 45.9 [35.8, 55.6] |
| E6 Haiku 4.5 | 85.5 [81.2, 89.5] | 85.5 [81.2, 89.5] | 81.7 [73.1, 89.2] | 45.2 [35.5, 54.8] |
| E7 regex->Jev | 84.0 [79.6, 88.3] | 84.0 [79.6, 88.3] | 68.8 [59.5, 77.4] | 38.4 [28.7, 48.0] |
| E8 regex->Sonnet | 84.9 [80.5, 89.1] | 84.9 [80.5, 89.1] | 72.0 [63.1, 80.6] | 41.6 [31.9, 51.3] |
| E9 regex->Jev->Sonnet | 84.6 [80.3, 88.8] | 84.6 [80.3, 88.8] | 73.8 [65.2, 82.4] | 45.5 [35.5, 55.2] |

### Seed vs sintético

Não se aplica ao test-v2: todos os 349 casos são `source: synthetic_v2` (google/gemini-2.5-flash); o test-v2 **não tem casos seed** (docs/dataset-card.md). A estratificação seed-vs-sintético se aplica apenas ao test-v1 (ver seção K quando as runs v1 forem concluídas).

## G. Taxas de flip entre repetições (determinismo)

flip de decisão = a escolha (skill, tool) difere entre as duas reps; flip de joint = a corretude difere. % [IC 95%] sobre os casos.

| verificação | casos | flips de decisão n (% [IC]) | flips de joint n (% [IC]) | nota |
|---|---|---|---|---|
| E1 regex (20 casos x 2) | 20 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) | rep 1 = cache hit da run principal; rep 2 nova |
| E6 Haiku 4.5 (60 casos x 2) | 60 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) | rep 1 = cache hit da run principal; rep 2 nova |
| E6b Qwen3-8B (50 casos x 2) | 50 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) | rep 1 = cache hit da run principal; rep 2 nova |
| E4 Jev: rep 1 vs rep 2 (349 casos) | 349 | 23 (6.6 [4.0, 9.2]) | 12 (3.4 [1.7, 5.4]) | dentro da run de 3 reps (amostras independentes) |
| E5 Sonnet 5: rep 1 vs rep 2 (349 casos) | 349 | 8 (2.3 [0.9, 4.0]) | 6 (1.7 [0.6, 3.2]) | dentro da run de 3 reps (amostras independentes) |
| E7 regex->Jev: rep 1 vs rep 2 (349 casos) | 349 | 23 (6.6 [4.0, 9.2]) | 11 (3.2 [1.4, 5.2]) | dentro da run de 3 reps (amostras independentes) |
| E8 regex->Sonnet: rep 1 vs rep 2 (349 casos) | 349 | 7 (2.0 [0.6, 3.4]) | 5 (1.4 [0.3, 2.9]) | dentro da run de 3 reps (amostras independentes) |
| E9 regex->Jev->Sonnet: rep 1 vs rep 2 (349 casos) | 349 | 20 (5.7 [3.4, 8.3]) | 13 (3.7 [2.0, 5.7]) | dentro da run de 3 reps (amostras independentes) |

## H. Mix de modelos servidos pelo Jev e acurácia por modelo servido (EXPLORATÓRIO, descritivo)

O Jev é um meta-router: cada chamada é servida por um modelo que ele escolhe. Acurácia = skill_correct (nível de skill) ou tool_correct dada uma skill correta (nível de tool), sobre as decisões que o Jev resolveu. O modelo servido é confundido com a dificuldade do caso (a escolha do Jev depende da entrada): sem leitura causal.

| run | nível | modelo servido | chamadas | share % | decisões resolvidas | acurácia % |
|---|---|---|---|---|---|---|
| E4 Jev | skill | deepseek/deepseek-v4.1-flash | 533 | 50.9 | 531 | 91.7 |
| E4 Jev | skill | openai/gpt-6-luna | 438 | 41.8 | 438 | 92.9 |
| E4 Jev | skill | google/gemini-3.8-flash | 67 | 6.4 | 67 | 100.0 |
| E4 Jev | skill | anthropic/claude-sonnet-5.5 | 6 | 0.6 | 6 | 100.0 |
| E4 Jev | skill | openai/gpt-6.1-sol | 3 | 0.3 | 3 | 100.0 |
| E4 Jev | tool | deepseek/deepseek-v4.1-flash | 727 | 69.5 | 670 | 90.9 |
| E4 Jev | tool | openai/gpt-6-luna | 203 | 19.4 | 197 | 94.9 |
| E4 Jev | tool | google/gemini-3.8-flash | 116 | 11.1 | 103 | 88.3 |
| E7 regex->Jev | skill | deepseek/deepseek-v4.1-flash | 285 | 57.9 | 285 | 95.4 |
| E7 regex->Jev | skill | openai/gpt-6-luna | 162 | 32.9 | 162 | 93.8 |
| E7 regex->Jev | skill | google/gemini-3.8-flash | 39 | 7.9 | 39 | 100.0 |
| E7 regex->Jev | skill | anthropic/claude-sonnet-5.5 | 3 | 0.6 | 3 | 100.0 |
| E7 regex->Jev | skill | openai/gpt-6.1-sol | 3 | 0.6 | 3 | 100.0 |
| E7 regex->Jev | tool | deepseek/deepseek-v4.1-flash | 735 | 70.2 | 636 | 90.6 |
| E7 regex->Jev | tool | openai/gpt-6-luna | 199 | 19.0 | 192 | 94.8 |
| E7 regex->Jev | tool | google/gemini-3.8-flash | 113 | 10.8 | 91 | 86.8 |
| E9 regex->Jev->Sonnet | skill | deepseek/deepseek-v4.1-flash | 332 | 57.9 | 252 | 94.4 |
| E9 regex->Jev->Sonnet | skill | openai/gpt-6-luna | 186 | 32.5 | 182 | 93.4 |
| E9 regex->Jev->Sonnet | skill | google/gemini-3.8-flash | 49 | 8.6 | 49 | 100.0 |
| E9 regex->Jev->Sonnet | skill | anthropic/claude-sonnet-5.5 | 3 | 0.5 | 3 | 100.0 |
| E9 regex->Jev->Sonnet | skill | openai/gpt-6.1-sol | 3 | 0.5 | 3 | 100.0 |
| E9 regex->Jev->Sonnet | tool | deepseek/deepseek-v4.1-flash | 736 | 70.3 | 632 | 92.1 |
| E9 regex->Jev->Sonnet | tool | openai/gpt-6-luna | 199 | 19.0 | 187 | 94.7 |
| E9 regex->Jev->Sonnet | tool | google/gemini-3.8-flash | 112 | 10.7 | 84 | 91.7 |

## I. Cascades

### Cobertura por etapa (runs reais; fração de linhas resolvidas em cada etapa, e a acurácia nela)

| run | estágio | resolvido por | linhas | share % | acurácia % (skill; tool dada skill correta) |
|---|---|---|---|---|---|
| E7 regex->Jev | skill | regex | 555 | 53.0 | 81.1 |
| E7 regex->Jev | skill | jev | 492 | 47.0 | 95.3 |
| E7 regex->Jev | tool | jev | 1047 | 100.0 | 91.1 |
| E8 regex->Sonnet | skill | llm | 573 | 54.7 | 93.4 |
| E8 regex->Sonnet | skill | regex | 474 | 45.3 | 85.4 |
| E8 regex->Sonnet | tool | llm | 1047 | 100.0 | 90.7 |
| E9 regex->Jev->Sonnet | skill | regex | 474 | 45.3 | 85.4 |
| E9 regex->Jev->Sonnet | skill | jev | 489 | 46.7 | 94.7 |
| E9 regex->Jev->Sonnet | skill | llm | 84 | 8.0 | 76.2 |
| E9 regex->Jev->Sonnet | tool | jev | 1009 | 96.4 | 92.6 |
| E9 regex->Jev->Sonnet | tool | llm | 38 | 3.6 | 69.0 |
| E12 hybrid->Jev->Sonnet (exploratório) | skill | hybrid | 906 | 86.5 | 90.4 |
| E12 hybrid->Jev->Sonnet (exploratório) | skill | jev | 100 | 9.6 | 96.0 |
| E12 hybrid->Jev->Sonnet (exploratório) | skill | llm | 41 | 3.9 | 65.9 |
| E12 hybrid->Jev->Sonnet (exploratório) | tool | jev | 1010 | 96.5 | 93.0 |
| E12 hybrid->Jev->Sonnet (exploratório) | tool | llm | 37 | 3.5 | 70.0 |

### Cascades simuladas no shadow pass do test-v2 (v2-shadow-tuned-routing-r3, 349 casos x 3 reps)

Replay das decisões registradas pelo mesmo código de pipeline (tabelas rápidas de `eval.calibrate`, conferidas contra `eval.simulate`). Joint ITT com etapa de tool que não pode ser reproduzida contada como 0 (limite inferior); custo sobre as linhas cobertas. Frozen = os thresholds pré-registrados; pontos de Pareto de dev = docs/results/cascade-pareto-dev.csv reproduzido em test (EXPLORATÓRIO, prereg §5). A última coluna compara com a run real (mesmas amostras).

**O joint simulado é um LIMITE INFERIOR.** O shadow pass registrou as decisões do estágio de tool apenas sob a skill que o E9 escolheu; quando uma cascade simulada escolhe uma skill diferente (correta), seu estágio de tool não pode ser reproduzido e conta 0 (coluna `unavail.`). É por isso que os pontos frozen de E7/E8 podem ficar abaixo das suas runs reais e que always-last (Sonnet / Jev sozinhos) fica abaixo das runs reais E5 / E4. Compare pontos simulados entre si, nunca com runs reais.

| cascade | status | ponto | thresholds de skill | thresholds de tool | joint % test [IC 95%] | linhas unavail. (de 1047) | US$/1k test [IC 95%] | joint % run real / dev |
|---|---|---|---|---|---|---|---|---|
| E7 | estimação | frozen (D5, método (a)) | regex=0.81 | - | 77.9 [73.7, 82.0] | 26 | 0.714 [0.640, 0.794] | 79.9 |
| E7 | exploratório | ponto de Pareto de dev | regex=0.63 | - | 70.3 [65.5, 74.9] | 29 | 0.636 [0.560, 0.717] | dev 76.2 @ 0.82 |
| E7 | exploratório | ponto de Pareto de dev | regex=0.74 | - | 77.1 [72.8, 81.2] | 27 | 0.683 [0.609, 0.762] | dev 78.8 @ 0.84 |
| E7 | exploratório | ponto de Pareto de dev | regex=0.81 | - | 77.9 [73.7, 82.0] | 26 | 0.714 [0.640, 0.794] | dev 79.5 @ 0.86 |
| E8 | estimação | frozen (D5, método (a)) | regex=0.88 | - | 80.4 [76.3, 84.4] | 10 | 4.345 [4.251, 4.442] | 81.5 |
| E8 | exploratório | ponto de Pareto de dev | regex=0.50 | - | 69.0 [64.2, 73.6] | 29 | 3.711 [3.660, 3.762] | dev 74.2 @ 4.66 |
| E8 | exploratório | ponto de Pareto de dev | regex=0.63 | - | 69.5 [64.8, 74.2] | 29 | 3.732 [3.676, 3.789] | dev 74.8 @ 4.68 |
| E8 | exploratório | ponto de Pareto de dev | regex=0.74 | - | 77.2 [72.8, 81.5] | 15 | 4.010 [3.932, 4.092] | dev 77.5 @ 4.77 |
| E8 | exploratório | ponto de Pareto de dev | regex=0.81 | - | 78.0 [73.7, 82.3] | 12 | 4.258 [4.164, 4.349] | dev 78.1 @ 5.02 |
| E8 | exploratório | ponto de Pareto de dev | regex=0.88 | - | 80.4 [76.3, 84.4] | 10 | 4.345 [4.251, 4.442] | dev 78.8 @ 5.17 |
| E9 | estimação | frozen (D5, método (a)) | regex=0.88, jev=0.76 | jev=0.5 | 81.9 [77.9, 85.7] | 0 | 1.002 [0.882, 1.131] | 81.8 |
| E9 | exploratório | ponto de Pareto de dev | regex=0.63, jev=0.73 | jev=0.50 | 70.4 [65.6, 75.0] | 29 | 0.766 [0.660, 0.885] | dev 76.2 @ 0.94 |
| E9 | exploratório | ponto de Pareto de dev | regex=0.74, jev=0.73 | jev=0.50 | 77.4 [73.2, 81.5] | 27 | 0.826 [0.722, 0.939] | dev 78.8 @ 0.96 |
| E9 | exploratório | ponto de Pareto de dev | regex=0.81, jev=0.73 | jev=0.50 | 78.2 [74.0, 82.3] | 26 | 0.856 [0.751, 0.970] | dev 79.5 @ 0.98 |
| E9 | exploratório | ponto de Pareto de dev | regex=0.88, jev=0.76 | jev=0.50 | 81.9 [77.9, 85.7] | 0 | 1.002 [0.882, 1.131] | dev 80.1 @ 1.20 |
| E12 | exploratório | frozen (D5, método (a)) | hybrid=0.83, jev=0.77 | jev=0.5 | 79.8 [75.6, 83.8] | 35 | 0.830 [0.717, 0.952] | 83.0 |
| E12 | exploratório | ponto de Pareto de dev | hybrid=0.79, jev=0.73 | jev=0.50 | 77.4 [73.1, 81.5] | 47 | 0.742 [0.641, 0.853] | dev 78.8 @ 0.90 |
| E12 | exploratório | ponto de Pareto de dev | hybrid=0.81, jev=0.73 | jev=0.50 | 78.5 [74.3, 82.5] | 39 | 0.760 [0.658, 0.875] | dev 79.5 @ 0.91 |
| E12 | exploratório | ponto de Pareto de dev | hybrid=0.83, jev=0.77 | jev=0.50 | 79.8 [75.6, 83.8] | 35 | 0.830 [0.717, 0.952] | dev 80.1 @ 1.02 |

### Referências no shadow de test (sem ajuste; mesma ressalva de limite inferior)

| cascade | referência | joint % | linhas unavail. | US$/1k |
|---|---|---|---|---|
| E7 | always-last (só o router final) | 79.8 [75.5, 83.8] | 66 | 0.755 [0.682, 0.832] |
| E7 | always-first (toda etapa aceita) | 69.7 [64.9, 74.3] | 29 | 0.637 [0.561, 0.719] |
| E7 | oracle (melhor etapa de parada por linha) | 84.4 [80.7, 87.9] | - | 0.494 [0.437, 0.555] |
| E7 | deferral aleatório nas taxas de aceitação dos thresholds frozen (200 sorteios, média) | 74.0 | - | 0.690 |
| E8 | always-last (só o router final) | 79.6 [75.3, 83.7] | 56 | 4.998 [4.925, 5.071] |
| E8 | always-first (toda etapa aceita) | 69.0 [64.2, 73.6] | 29 | 3.711 [3.660, 3.762] |
| E8 | oracle (melhor etapa de parada por linha) | 83.8 [79.9, 87.4] | - | 3.194 [3.066, 3.321] |
| E8 | deferral aleatório nas taxas de aceitação dos thresholds frozen (200 sorteios, média) | 74.3 | - | 4.401 |
| E9 | always-last (só o router final) | 79.6 [75.3, 83.7] | 56 | 5.768 [5.668, 5.873] |
| E9 | always-first (toda etapa aceita) | 69.9 [65.1, 74.5] | 29 | 0.652 [0.573, 0.737] |
| E9 | oracle (melhor etapa de parada por linha) | 86.9 [83.4, 90.3] | - | 0.780 [0.690, 0.874] |
| E9 | deferral aleatório nas taxas de aceitação dos thresholds frozen (200 sorteios, média) | 75.0 | - | 0.972 |
| E12 | always-last (só o router final) | 79.6 [75.3, 83.7] | 56 | 5.768 [5.668, 5.873] |
| E12 | always-first (toda etapa aceita) | 75.6 [71.2, 79.9] | 44 | 0.601 [0.531, 0.676] |
| E12 | oracle (melhor etapa de parada por linha) | 86.9 [83.4, 90.3] | - | 0.748 [0.663, 0.838] |
| E12 | deferral aleatório nas taxas de aceitação dos thresholds frozen (200 sorteios, média) | 76.2 | - | 0.810 |

A referência always-last de E8/E9 é "always-LLM" (Sonnet sozinho em todos os estágios, sobre as amostras do Sonnet no shadow); o always-last de E7 é o Jev sozinho. O oracle é um limite superior para qualquer regra de deferral; uma regra de threshold só vale algo se superar o deferral aleatório nas mesmas taxas de aceitação. Uma fronteira de Pareto in-sample ajustada em test (otimista, exploratória) está em estimation.json (`cascades.shadow.<E>.test_insample_front`) e desenhada em traço claro na figura de Pareto.

## J. End-to-end (executor Sonnet 5, 1 rep, 349 casos; ITT, % [IC 95%])

e2e_success = first call + clarification + recovered (disjuntos, docs/metrics.md). args_invented e entity_grounded não se aplicam a linhas com erro.

| run | linhas | erros | skill | tool first call | args válidos | e2e_success | = first call | + clarification | + recovered | e2e_strict | args_invented (taxa, menor = melhor) | entity_grounded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E0 nativo (sem router) | 349 | 0 | 88.8 [85.4, 92.0] | 75.1 [70.5, 79.7] | 68.5 [63.3, 73.4] | 55.6 [50.1, 60.7] | 53.3 [47.9, 58.5] | 1.4 [0.3, 2.9] | 0.9 [0.0, 2.0] | 55.6 [50.1, 60.7] | 0.4 [0.0, 1.1] | 98.0 [96.5, 99.4] |
| E1 regex | 349 | 0 | 75.6 [71.1, 79.9] | 57.9 [52.7, 63.0] | 55.0 [49.9, 60.2] | 34.7 [29.8, 39.5] | 34.1 [29.2, 39.0] | 0.3 [0.0, 0.9] | 0.3 [0.0, 0.9] | 34.7 [29.8, 39.5] | 0.4 [0.0, 1.3] | 97.3 [94.9, 99.2] |
| E5 Sonnet 5 | 349 | 0 | 89.4 [86.0, 92.6] | 75.1 [70.5, 79.7] | 68.2 [63.3, 73.1] | 50.7 [45.3, 55.9] | 49.9 [44.4, 55.3] | 0.9 [0.0, 2.0] | 0.0 [0.0, 0.0] | 50.7 [45.3, 55.9] | 0.4 [0.0, 1.1] | 98.0 [96.6, 99.4] |
| E6b Qwen3-8B local | 349 | 0 | 83.1 [79.1, 87.1] | 74.8 [69.9, 79.4] | 67.6 [62.5, 72.5] | 46.4 [41.3, 51.6] | 45.3 [40.1, 50.7] | 0.9 [0.0, 2.0] | 0.3 [0.0, 0.9] | 46.4 [41.3, 51.6] | 0.3 [0.0, 1.0] | 98.0 [96.3, 99.4] |
| E7 regex->Jev | 349 | 0 | 83.7 [79.7, 87.4] | 73.9 [69.1, 78.5] | 67.0 [61.9, 71.9] | 45.0 [39.8, 50.1] | 43.6 [38.4, 48.7] | 1.1 [0.3, 2.3] | 0.3 [0.0, 0.9] | 45.0 [39.8, 50.1] | 0.4 [0.0, 1.1] | 98.0 [96.3, 99.4] |
| E9 regex->Jev->Sonnet | 349 | 0 | 85.4 [81.7, 89.1] | 73.9 [69.3, 78.5] | 66.2 [61.0, 71.1] | 45.8 [40.4, 51.0] | 45.0 [39.8, 50.1] | 0.9 [0.0, 2.0] | 0.0 [0.0, 0.0] | 45.8 [40.4, 51.0] | 0.4 [0.0, 1.1] | 97.7 [96.0, 99.1] |
| E11 híbrido | 349 | 0 | 82.8 [78.8, 86.8] | 71.3 [66.5, 75.9] | 66.8 [61.6, 71.6] | 44.4 [39.3, 49.6] | 43.3 [38.1, 48.4] | 1.1 [0.3, 2.3] | 0.0 [0.0, 0.0] | 44.4 [39.3, 49.6] | 0.4 [0.0, 1.1] | 98.3 [96.8, 99.4] |

### Custo por turno e contexto

US$ por 1 000 turnos (observed = registrado; list = sem desconto de prompt cache, Jev reportado). Contexto = tokens de prompt do executor por turno (todas as chamadas do agente).

| run | US$/1k turnos total [IC] | routing [IC] | executor [IC] | list uncached total [IC] | tokens de prompt do executor/turno [IC] | fração em cache dos tokens de prompt % | tokens de completion/turno [IC] | chamadas do executor/turno |
|---|---|---|---|---|---|---|---|---|
| E0 nativo (sem router) | 9.03 [8.53, 9.58] | 0.00 [0.00, 0.00] | 9.03 [8.53, 9.58] | 33.14 [31.53, 34.81] | 14737 [13994, 15516] | 91.0 | 367 [347, 388] | 2.79 |
| E1 regex | 5.93 [5.37, 6.51] | 0.00 [0.00, 0.00] | 5.93 [5.37, 6.51] | 17.20 [15.86, 18.56] | 7188 [6629, 7752] | 87.7 | 282 [255, 311] | 1.56 |
| E5 Sonnet 5 | 11.84 [11.39, 12.33] | 5.05 [4.95, 5.16] | 6.79 [6.38, 7.24] | 32.23 [31.28, 33.22] | 8605 [8238, 8987] | 88.5 | 321 [302, 341] | 1.97 |
| E6b Qwen3-8B local | 7.90 [7.41, 8.43] | 0.00 [0.00, 0.00] | 7.90 [7.41, 8.43] | 21.14 [20.26, 22.08] | 8877 [8507, 9271] | 84.5 | 339 [318, 361] | 1.98 |
| E7 regex->Jev | 7.87 [7.40, 8.37] | 0.76 [0.68, 0.84] | 7.11 [6.66, 7.59] | 21.95 [20.98, 22.96] | 8858 [8461, 9278] | 88.7 | 347 [323, 373] | 1.99 |
| E9 regex->Jev->Sonnet | 8.21 [7.72, 8.73] | 1.01 [0.88, 1.14] | 7.20 [6.74, 7.69] | 22.14 [21.19, 23.14] | 8734 [8340, 9142] | 87.4 | 333 [311, 357] | 1.97 |
| E11 híbrido | 7.45 [6.95, 7.98] | 0.00 [0.00, 0.00] | 7.45 [6.95, 7.98] | 21.45 [20.44, 22.50] | 8956 [8532, 9391] | 87.5 | 354 [330, 379] | 2.00 |

### Variância do executor (segunda run e2e em 60 casos; routers são cache hits, executor reamostrado)

| exp | run | casos | flip de e2e_success % [IC] | e2e_success principal -> rep2 (mesmos casos) |
|---|---|---|---|---|
| E0 | v2-e0-native-e2e-rep2-60 | 60 | 5.0 [0.0, 11.7] | 48.3 -> 53.3 |
| E9 | v2-e9-tuned-e2e-rep2-60 | 60 | 1.7 [0.0, 5.0] | 45.0 -> 43.3 |

## K. Seções reservadas (preenchidas quando as runs forem concluídas)

### Replicação dos routers gratuitos no test-v1 (split exposto) (EXPLORATÓRIO: verificação de contaminação)

| router | run | linhas | joint % test-v1 | joint % test-v2 | fontes |
|---|---|---|---|---|---|
| E1 | v1-e1-regex-routing-r1 | 349 | 60.5 [55.3, 65.6] | 52.7 [47.3, 57.9] | fonte ausente nas linhas |
| E2 | v1-e2-bm25-routing-r1 | 349 | 53.0 [47.9, 58.2] | 49.0 [43.8, 54.2] | fonte ausente nas linhas |
| E3 | v1-e3-embedding-routing-r1 | 349 | 80.5 [76.2, 84.5] | 73.6 [68.8, 78.2] | fonte ausente nas linhas |
| E10 | v1-e10-classifier-routing-r1 | 349 | 76.8 [72.2, 81.1] | 74.8 [70.2, 79.4] | fonte ausente nas linhas |
| E11 | v1-e11-hybrid-routing-r1 | 349 | 76.5 [71.9, 80.8] | 72.8 [67.9, 77.4] | fonte ausente nas linhas |

### RQ5 leave-tools-out (EXPLORATÓRIO; tabela de `study rq5`, sem cronometragem de re-treino)

## RQ5 leave-tools-out — split `test_v2`

Retidas: `get_refund_status`, `reschedule_delivery`, `generate_return_label`. affected = casos com uma tool retida entre as tools aceitáveis; other = o restante. Δ other / lost / won são pareados com `base` (conjunta, casos other); stolen = casos other roteados para uma tool retida. Erros contam como errados (ITT).

| strategy | cond | n aff | joint aff | skill aff | pred∈H aff | n other | joint other | lost | won | Δ other (pp) | stolen | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | base | 48 | 0.0 | 77.1 | 0.0 | 301 | 51.2 | – | – | – | 0 | 0 |
| bm25 | zero | 48 | 54.2 | 85.4 | 54.2 | 301 | 48.2 | 10 | 1 | -3.0 | 11 | 0 |
| classifier | base | 48 | 14.6 | 77.1 | 0.0 | 301 | 75.1 | – | – | – | 0 | 0 |
| classifier | zero | 48 | 83.3 | 91.7 | 68.8 | 301 | 73.4 | 10 | 5 | -1.7 | 10 | 0 |
| embedding | base | 48 | 14.6 | 85.4 | 0.0 | 301 | 74.8 | – | – | – | 0 | 0 |
| embedding | zero | 48 | 89.6 | 97.9 | 75.0 | 301 | 71.1 | 12 | 1 | -3.7 | 9 | 0 |
| haiku | base | 48 | 14.6 | 97.9 | 0.0 | 60 | 78.3 | – | – | – | 0 | 0 |
| haiku | zero | 48 | 95.8 | 97.9 | 85.4 | 60 | 75.0 | 3 | 1 | -3.3 | 0 | 0 |
| hybrid | base | 48 | 12.5 | 85.4 | 0.0 | 301 | 74.4 | – | – | – | 0 | 0 |
| hybrid | zero | 48 | 58.3 | 89.6 | 45.8 | 301 | 73.8 | 3 | 1 | -0.7 | 1 | 0 |
| hybrid | eng | 48 | 66.7 | 89.6 | 54.2 | 301 | 73.1 | 5 | 1 | -1.3 | 2 | 0 |
| hybrid | full | 48 | 66.7 | 89.6 | 54.2 | 301 | 73.8 | 3 | 1 | -0.7 | 1 | 0 |
| jev | base | 48 | 16.7 | 100.0 | 0.0 | 60 | 76.7 | – | – | – | 0 | 1 |
| jev | zero | 48 | 93.8 | 95.8 | 81.2 | 60 | 76.7 | 2 | 2 | +0.0 | 0 | 0 |
| regex | base | 48 | 10.4 | 83.3 | 0.0 | 301 | 53.8 | – | – | – | 0 | 0 |
| regex | zero | 48 | 10.4 | 83.3 | 0.0 | 301 | 53.8 | 0 | 0 | +0.0 | 0 | 0 |
| regex | eng | 48 | 50.0 | 83.3 | 39.6 | 301 | 53.5 | 1 | 0 | -0.3 | 2 | 0 |
| regex | full | 48 | 45.8 | 83.3 | 35.4 | 301 | 53.8 | 0 | 0 | +0.0 | 2 | 0 |
| sonnet | base | 48 | 16.7 | 97.9 | 0.0 | 60 | 76.7 | – | – | – | 0 | 0 |
| sonnet | zero | 48 | 93.8 | 97.9 | 87.5 | 60 | 80.0 | 0 | 2 | +3.3 | 0 | 0 |

### Esforço de adicionar as 3 tools

- Entrada de catálogo (input de toda estratégia, a adição com esforço zero): 18 linhas de descrição, 12 exemplos, 15 keywords.
- Regex, engenheirado (`eng`): 30 linhas, 17 regras, 5 defs, 1.2 min de relógio (timebox de 20 min; agente de IA (Claude Opus): regras escritas pelo agente, com timebox; não é um engenheiro humano).
- Regex, produção (`full`, referência): 17 linhas, 8 regras, 2 defs; minutos não registrados (iterado no dev).
- Regex, esforço zero: nada novo (a tool é inalcançável pelo regex).

