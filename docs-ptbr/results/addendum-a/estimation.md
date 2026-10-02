# Tabelas de estimação da Parte A (SÓ ESTIMAÇÃO: prereg-v2a §3 'Estimation only'; ICs, sem testes)

> Tradução pt-BR de [`docs/results/addendum-a/estimation.md`](../../../docs/results/addendum-a/estimation.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

Gerado por `scripts/analysis/addendum_a.py`. ITT; ICs 95% = bootstrap por cluster sobre os ids de caso (10k, seed 20260930). A família A confirmatória está em primary.md. Braços: os seis roteadores gerenciados da Parte A (test-v2, 349 casos, 1 rep) e as referências locais da fase 1 reaproveitadas E6b, E3, E10 (mesmos 349 casos; só leitura).

## A. Por braço (só roteamento, ITT; % com IC 95% por bootstrap por cluster)

| roteador | status | linhas | reps | linhas de erro | skill % | tool % dado skill certa | conjunta % (métrica primária) | conjunta só primeiro rótulo % (estrita) | abstain_correct % | recall@1 | recall@2 | recall@3 | precisão da abstenção % (n abstidos) | recall da abstenção % (n esperados) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E3c roteador Cohere Embed v4 | confirmatório (A3) | 349 | 1 | 0 (0.0%) | 74.5 [69.9, 79.1] | 73.1 [67.7, 78.5] | 54.4 [49.3, 59.6] | 49.9 [44.7, 55.0] | 87.4 [83.7, 90.8] | 54.4 [49.3, 59.6] | 67.0 [62.2, 71.9] | 70.8 [65.9, 75.4] | 92.3 (13) | 21.8 (55) |
| E3t roteador Titan v2 | confirmatório (A4) | 349 | 1 | 0 (0.0%) | 72.8 [67.9, 77.4] | 76.8 [71.3, 81.9] | 55.9 [50.4, 61.0] | 51.0 [45.6, 56.2] | 89.1 [85.7, 92.3] | 55.9 [50.4, 61.0] | 65.9 [60.7, 70.8] | 70.2 [65.3, 75.1] | 69.4 (49) | 58.2 (55) |
| E10c sonda sobre vetores Cohere | estimação | 349 | 1 | 0 (0.0%) | 71.1 [66.2, 75.9] | 77.8 [72.6, 82.7] | 55.3 [50.1, 60.5] | 52.1 [47.0, 57.3] | 86.5 [82.8, 90.0] | 55.3 [50.1, 60.5] | 63.6 [58.5, 68.5] | 66.5 [61.6, 71.3] | 56.3 (71) | 70.9 (55) |
| E10t sonda sobre vetores Titan | estimação | 349 | 1 | 0 (0.0%) | 70.5 [65.6, 75.1] | 72.4 [66.7, 78.0] | 51.0 [45.6, 56.2] | 47.9 [42.4, 53.0] | 84.5 [80.5, 88.3] | 51.0 [45.6, 56.2] | 61.9 [56.7, 66.8] | 65.0 [59.9, 69.9] | 50.7 (71) | 65.5 (55) |
| E6m Ministral 3 8B | confirmatório (A1) | 349 | 1 | 2 (0.6%) | 88.5 [85.1, 91.7] | 92.9 [90.0, 95.5] | 82.2 [77.9, 86.2] | 71.9 [67.0, 76.5] | 95.7 [93.4, 97.7] | 82.2 [77.9, 86.2] | 86.8 [83.1, 90.3] | 88.0 [84.5, 91.1] | 95.7 (47) | 80.0 (55) |
| E6n Nemotron Nano 9B v2 | confirmatório (A2) | 349 | 1 | 0 (0.0%) | 85.4 [81.7, 89.1] | 90.3 [86.9, 93.6] | 77.1 [72.5, 81.4] | 71.3 [66.5, 75.9] | 92.8 [90.0, 95.4] | 77.1 [72.5, 81.4] | 83.4 [79.4, 87.1] | 84.2 [80.5, 88.0] | 81.2 (48) | 70.9 (55) |
| E6b Qwen3-8B local (fase 1) | reference (fase 1, reaproveitado) | 349 | 1 | 0 (0.0%) | 87.1 [83.7, 90.5] | 91.8 [88.5, 94.7] | 79.9 [75.6, 84.0] | 70.8 [65.9, 75.4] | 97.1 [95.4, 98.9] | 79.9 [75.6, 84.0] | 85.7 [81.9, 89.1] | 86.5 [82.8, 90.0] | 94.5 (55) | 87.3 (55) |
| E3 qwen3-embedding 8B local (fase 1) | reference (fase 1, reaproveitado) | 349 | 1 | 0 (0.0%) | 85.1 [81.4, 88.8] | 86.5 [82.5, 90.2] | 73.6 [68.8, 78.2] | 67.0 [61.9, 71.9] | 95.1 [92.8, 97.4] | 73.6 [68.8, 78.2] | 83.4 [79.4, 87.1] | 84.8 [81.1, 88.5] | 100.0 (40) | 69.1 (55) |
| E10 sonda local (fase 1) | reference (fase 1, reaproveitado) | 349 | 1 | 0 (0.0%) | 87.1 [83.4, 90.5] | 85.9 [81.9, 89.5] | 74.8 [70.2, 79.4] | 67.9 [63.0, 72.8] | 92.0 [88.8, 94.6] | 74.8 [70.2, 79.4] | 82.2 [78.2, 86.2] | 84.8 [80.8, 88.5] | 74.6 (63) | 78.2 (55) |

### Custo de roteamento por 1 000 casos (US$), três regimes

- **observado**: `cost_usd.routing` como gravado por linha (o regime da co-primária de H1 da fase 1): o custo gravado de cada estágio consultado. Nos roteadores por embedding cada estágio grava o embedding da consulta; o estágio de tool do E3c/E3t reaproveita o vetor da consulta em cache, então o custo faturado (§C) é cerca de metade disso;
- **tabela sem cache**: tokens gravados × preço de tabela (`config/prices.yaml`; Ministral 3 8B e Nemotron Nano 2 pela maior das duas tarifas listadas em sa-east-1, embeddings pelo preço de tabela de us-east-1), sem desconto de cache de prompt; local = 0;
- **cache modelado**: o modelo Poisson/TTL da fase 1 (TTL de 5 minutos renovado a cada acerto, por prefixo de prompt). Nenhum dos modelos da Parte A tem preço de cache nem leitura de cache observada, então o regime modelado é igual à tabela sem cache em todo braço da Parte A (uma afirmação de modelo, não uma medição).

| roteador | observado [IC 95%] | tabela sem cache [IC 95%] | modelado @ 0.01 QPS | modelado @ 0.1 QPS | modelado @ 1 QPS | modelado @ 10 QPS | modelado ∞ |
|---|---|---|---|---|---|---|---|
| E3c roteador Cohere Embed v4 | 0.009 [0.008, 0.010] | 0.009 [0.008, 0.010] | 0.009 | 0.009 | 0.009 | 0.009 | 0.009 |
| E3t roteador Titan v2 | 0.001 [0.001, 0.001] | 0.001 [0.001, 0.001] | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 |
| E10c sonda sobre vetores Cohere | 0.007 [0.007, 0.008] | 0.007 [0.007, 0.008] | 0.007 | 0.007 | 0.007 | 0.007 | 0.007 |
| E10t sonda sobre vetores Titan | 0.001 [0.001, 0.001] | 0.001 [0.001, 0.001] | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 |
| E6m Ministral 3 8B | 0.441 [0.434, 0.448] | 0.441 [0.434, 0.448] | 0.441 | 0.441 | 0.441 | 0.441 | 0.441 |
| E6n Nemotron Nano 9B v2 | 0.222 [0.220, 0.225] | 0.222 [0.220, 0.225] | 0.222 | 0.222 | 0.222 | 0.222 | 0.222 |
| E6b Qwen3-8B local (fase 1) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E3 qwen3-embedding 8B local (fase 1) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| E10 sonda local (fase 1) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

### C. Custo de roteamento faturado por 1 000 casos (US$; `cost_usd.routing_billed`)

O que o provedor cobrou pelas chamadas de roteamento da run (acertos do cache de respostas e reuso do vetor da consulta faturam 0). E10c/E10t mostram 0: o guarda de orçamento precifica os embeddings de consulta da sonda no Bedrock como grátis (nota do prereg-v2a §6); o custo real deles é a coluna de tabela sem cache do §A.

| braço | US$/1k faturado [IC 95%] | US$/1k observado [IC 95%] |
|---|---|---|
| E3c roteador Cohere Embed v4 | 0.0045 [0.0042, 0.0048] | 0.0090 [0.0085, 0.0095] |
| E3t roteador Titan v2 | 0.0007 [0.0007, 0.0007] | 0.0014 [0.0013, 0.0014] |
| E10c sonda sobre vetores Cohere | 0.0001 [0.0000, 0.0001] | 0.0072 [0.0068, 0.0075] |
| E10t sonda sobre vetores Titan | 0.0000 [0.0000, 0.0000] | 0.0012 [0.0011, 0.0013] |
| E6m Ministral 3 8B | 0.4413 [0.4342, 0.4484] | 0.4413 [0.4342, 0.4484] |
| E6n Nemotron Nano 9B v2 | 0.2225 [0.2201, 0.2248] | 0.2225 [0.2201, 0.2248] |
| E6b Qwen3-8B local (fase 1) | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] |
| E3 qwen3-embedding 8B local (fase 1) | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] |
| E10 sonda local (fase 1) | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] |

## B. Sondas vs o seu par local e vs o seu próprio roteador por embedding (ESTIMAÇÃO: Δ pareado, sem teste)

Bootstrap pareado por cluster sobre os 349 casos compartilhados (10k, seed 20260930), ITT.

| contraste | Δ conjunta pp [IC 95%] | Δ skill pp [IC 95%] |
|---|---|---|
| E10c − E10 | -19.5 [-24.6, -14.6] | -16.0 [-20.3, -11.7] |
| E10t − E10 | -23.8 [-29.2, -18.3] | -16.6 [-21.2, -12.0] |
| E10c − E3c | 0.9 [-4.6, 6.3] | -3.4 [-8.3, 1.4] |
| E10t − E3t | -4.9 [-9.2, -0.6] | -2.3 [-6.0, 1.4] |

## D. Calibração no test-v2: Brier / ECE (10 bins de mesma massa), bruto × calibrado no dev

Por decisão tomada (abstenções e linhas de erro fora); nível de tool só nas linhas com skill certa. `raw` = o score do próprio roteador (usage raw_confidence / confidence_raw); `deployed` = a confiança que a run usou (mapa do dev aplicado onde a regra pré-registrada ece_cal < ece_raw o manteve); `dev map` = o mapa ajustado no dev aplicado a toda decisão que tem um, incluindo estágios de LLM em que ele NÃO foi implantado (post hoc, exploratório). Nas cascatas usa-se o score do passo que resolveu.

| roteador | nível | n decisões | Brier / ECE bruto | Brier / ECE implantado | Brier / ECE mapa do dev | mapa usado (decisões) |
|---|---|---|---|---|---|---|
| E3c roteador Cohere Embed v4 | skill | 349 | 0.172 / 0.093 | 0.165 / 0.060 | 0.165 / 0.060 | implantado 349 |
| E3c roteador Cohere Embed v4 | tool | 260 | 0.206 / 0.183 | 0.175 / 0.128 | 0.175 / 0.128 | implantado 260 |
| E3t roteador Titan v2 | skill | 349 | 0.172 / 0.098 | 0.178 / 0.120 | 0.178 / 0.120 | implantado 349 |
| E3t roteador Titan v2 | tool | 254 | 0.169 / 0.114 | 0.194 / 0.171 | 0.194 / 0.171 | implantado 254 |
| E10c sonda sobre vetores Cohere | skill | 349 | 0.198 / 0.138 | 0.198 / 0.138 | 0.198 / 0.138 | nenhum 349 |
| E10c sonda sobre vetores Cohere | tool | 248 | 0.286 / 0.383 | 0.152 / 0.180 | 0.152 / 0.180 | implantado 248 |
| E10t sonda sobre vetores Titan | skill | 349 | 0.398 / 0.439 | 0.180 / 0.057 | 0.180 / 0.057 | implantado 349 |
| E10t sonda sobre vetores Titan | tool | 246 | 0.483 / 0.538 | 0.190 / 0.169 | 0.190 / 0.169 | implantado 246 |
| E6m Ministral 3 8B | skill | 347 | 0.103 / 0.107 | 0.090 / 0.145 | 0.090 / 0.145 | implantado 347 |
| E6m Ministral 3 8B | tool | 309 | 0.069 / 0.096 | 0.084 / 0.171 | 0.084 / 0.171 | implantado 309 |
| E6n Nemotron Nano 9B v2 | skill | 349 | 0.129 / 0.154 | 0.122 / 0.186 | 0.122 / 0.186 | implantado 349 |
| E6n Nemotron Nano 9B v2 | tool | 298 | 0.090 / 0.119 | 0.098 / 0.223 | 0.098 / 0.223 | implantado 298 |
| E6b Qwen3-8B local (fase 1) | skill | 349 | 0.116 / 0.155 | 0.113 / 0.190 | 0.113 / 0.190 | implantado 349 |
| E6b Qwen3-8B local (fase 1) | tool | 304 | 0.079 / 0.105 | 0.083 / 0.198 | 0.083 / 0.198 | implantado 304 |
| E3 qwen3-embedding 8B local (fase 1) | skill | 349 | 0.118 / 0.060 | 0.114 / 0.063 | 0.114 / 0.063 | implantado 349 |
| E3 qwen3-embedding 8B local (fase 1) | tool | 297 | 0.092 / 0.040 | 0.098 / 0.070 | 0.098 / 0.070 | implantado 297 |
| E10 sonda local (fase 1) | skill | 349 | 0.184 / 0.292 | 0.096 / 0.051 | 0.096 / 0.051 | implantado 349 |
| E10 sonda local (fase 1) | tool | 304 | 0.310 / 0.451 | 0.107 / 0.095 | 0.107 / 0.095 | implantado 304 |

## D2. Predição seletiva: risco × cobertura na conjunta (confiança = min(skill, tool))

| roteador | AURC (menor = melhor) | cobertura % com risco <= 5% | conjunta % com cobertura total |
|---|---|---|---|
| E3c roteador Cohere Embed v4 | 0.264 | 0.0 | 54.4 |
| E3t roteador Titan v2 | 0.278 | 0.6 | 55.9 |
| E10c sonda sobre vetores Cohere | 0.243 | 1.1 | 55.3 |
| E10t sonda sobre vetores Titan | 0.278 | 0.0 | 51.0 |
| E6m Ministral 3 8B | 0.123 | 0.9 | 82.2 |
| E6n Nemotron Nano 9B v2 | 0.213 | 0.0 | 77.1 |
| E6b Qwen3-8B local (fase 1) | 0.181 | 11.5 | 79.9 |
| E3 qwen3-embedding 8B local (fase 1) | 0.109 | 40.4 | 73.6 |
| E10 sonda local (fase 1) | 0.097 | 17.5 | 74.8 |

## E. Taxas de erro e de falha de parse (ESTIMAÇÃO; ITT)

Linha de erro = a linha reescorada carrega um erro (contada como errada no ITT). Falha de parse = uma chamada de estágio cuja saída estruturada falhou na validação (`usage.parse_fail`); o rescore a transforma em linha de erro, embora o log do manifesto tenha contado 0 erros de infra (o mesmo mecanismo das 2 linhas E4 Jev da fase 1). Chamadas de estágio = chamadas dos estágios de skill + tool (2 por linha).

| braço | linhas | linhas de erro n (% [IC 95%]) | tipos | chamadas de estágio | chamadas com falha de parse n (% das chamadas) | chamadas com retentativa do provedor |
|---|---|---|---|---|---|---|
| E3c roteador Cohere Embed v4 | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E3t roteador Titan v2 | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E10c sonda sobre vetores Cohere | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E10t sonda sobre vetores Titan | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E6m Ministral 3 8B | 349 | 2 (0.6 [0.0, 1.4]) | llm: parse_fail ×2 | 698 | 2 (0.29%) | 0 |
| E6n Nemotron Nano 9B v2 | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E6b Qwen3-8B local (fase 1) | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E3 qwen3-embedding 8B local (fase 1) | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |
| E10 sonda local (fase 1) | 349 | 0 (0.0 [0.0, 0.0]) | - | 698 | 0 (0.00%) | 0 |

## F. Taxa de mudança rep 1 × rep 2 nos 50 casos estratificados (ESTIMAÇÃO)

Rep 1 = acerto de cache da run r1 (conferido: a última coluna conta as decisões da rep 1 que diferem da linha r1; 0 = idênticas), rep 2 = uma chamada nova a temperatura 0. mudança de decisão = a escolha (skill, tool) difere; mudança de acerto = o acerto difere. % [IC 95%] sobre casos.

| braço | run | casos | mudanças de decisão n (% [IC]) | mudanças de acerto conjunto n (% [IC]) | decisões rep-1 ≠ r1 |
|---|---|---|---|---|---|
| E6m Ministral 3 8B (50 casos x 2) | v2a-e6m-ministral-canonical-repeat50 | 50 | 2 (4.0 [0.0, 10.0]) | 1 (2.0 [0.0, 6.0]) | 0 |
| E6n Nemotron Nano 9B v2 (50 casos x 2) | v2a-e6n-nemotron-canonical-repeat50 | 50 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) | 0 |
| E6b Qwen3-8B local, fase 1 (contexto, 50 casos x 2) | v2-e6b-qwen-canonical-repeat50 | 50 | 0 (0.0 [0.0, 0.0]) | 0 (0.0 [0.0, 0.0]) | 0 |

## G. Latência (ESTIMAÇÃO; só benchmark dedicado)

Os 100 casos estratificados do test-v2 da fase 1 (`config/manifest/latency_test_v2_b{1..4}.ids`) em 4 blocos de 25, intercalação por bloco, concorrência 1, caches de resposta desligados, cache de vetores novo (`.cache/latency-a`). Latência de roteamento (estágio de skill + tool) por caso. O primeiro caso de cada bloco é **frio** e reportado à parte (mediana / máx dos 4); os outros 96 são **quentes**; as linhas de erro (falhas de parse transformadas em erro pelo rescore) ficam fora do conjunto quente e contam na coluna de erro (regra da fase 1). ICs 95%: bootstrap por cluster sobre casos (10k, seed 20260930); o p99 de 96 valores fica perto do máximo da amostra (um indicador de cauda). Os números de acurácia vêm das runs de 349 casos, não deste benchmark (a conjunta dos seus 100 casos aparece só como referência).

### G1. Mesma janela: os seis braços gerenciados novos e as âncoras gerenciadas (Parte A, intercalados por bloco)

| estratégia | janela | onde | n quente | p50 ms [IC 95%] | p95 ms [IC 95%] | p99 ms [IC 95%] | primeiro caso frio ms mediana / máx | linhas de erro | conjunta no benchmark % (100 casos) |
|---|---|---|---|---|---|---|---|---|---|
| E3c Cohere v4 | Parte A | Bedrock | 96 | 650 [594, 780] | 1665 [1466, 2927] | 3077 [1677, 3418] | 2010 / 4436 | 0 | 54.0 |
| E3t Titan v2 | Parte A | Bedrock | 96 | 170 [157, 187] | 610 [416, 910] | 937 [616, 1078] | 1687 / 7300 | 0 | 47.0 |
| E10c sonda/Cohere | Parte A | Bedrock | 96 | 635 [585, 729] | 1522 [1386, 2128] | 3075 [1545, 3417] | 844 / 4433 | 0 | 52.0 |
| E10t sonda/Titan | Parte A | Bedrock | 96 | 162 [153, 174] | 506 [261, 907] | 934 [511, 1076] | 305 / 3020 | 0 | 49.0 |
| E6m Ministral 3 8B | Parte A | Bedrock | 94 | 1010 [999, 1019] | 1584 [1124, 1958] | 2056 [1577, 2511] | 691 / 1061 | 2 | 79.0 |
| E6n Nemotron 9B | Parte A | Bedrock | 96 | 1236 [1229, 1283] | 1465 [1384, 1744] | 1769 [1474, 2136] | 1398 / 1413 | 0 | 75.0 |
| E4 Jev (âncora) | Parte A | OpenRouter | 95 | 4396 [4131, 4735] | 8128 [6939, 9590] | 9732 [7758, 10140] | 3191 / 3892 | 1 | 86.0 |
| E6 Haiku 4.5 (âncora) | Parte A | Bedrock | 96 | 3311 [3252, 3480] | 4883 [4504, 5594] | 5966 [4892, 6636] | 3151 / 3166 | 0 | 82.0 |

### G2. Outra janela: blocos locais da fase 1 (e os blocos de âncora da fase 1 usados para a deriva)

**Ressalva de janela (prereg-v2a §3, obrigatória):** as linhas locais são os blocos lat-* da fase 1, medidos numa janela de tempo diferente da dos blocos da Parte A; o mesmo Mac (M5 Pro 48 GB) no lado local, Bedrock `sa-east-1` (Jev: OpenRouter) chamado desse Mac no lado gerenciado. A deriva é estimada pelas âncoras gerenciadas (Jev, Haiku 4.5) rodadas de novo nas duas janelas; é reportada, nunca subtraída.

| estratégia | janela | onde | n quente | p50 ms [IC 95%] | p95 ms [IC 95%] | p99 ms [IC 95%] | primeiro caso frio ms mediana / máx | linhas de erro | conjunta no benchmark % (100 casos) |
|---|---|---|---|---|---|---|---|---|---|
| E6b Qwen3-8B local | fase 1 | local (Mac) | 96 | 9875 [8726, 9960] | 11983 [10394, 12264] | 12366 [11988, 12559] | 6675 / 10012 | 0 | 78.0 |
| E3 qwen3-emb 8B local | fase 1 | local (Mac) | 96 | 427 [419, 436] | 710 [574, 1492] | 1514 [702, 1559] | 493 / 8921 | 0 | 71.0 |
| E10 sonda local | fase 1 | local (Mac) | 96 | 419 [413, 425] | 1048 [635, 4634] | 5093 [1178, 5490] | 465 / 509 | 0 | 71.0 |
| E4 Jev (âncora) | fase 1 | OpenRouter | 96 | 4308 [4066, 4576] | 6851 [6303, 7531] | 7789 [6835, 11560] | 3015 / 5718 | 0 | 83.0 |
| E6 Haiku 4.5 (âncora) | fase 1 | Bedrock | 96 | 3507 [3421, 3648] | 5919 [5027, 6861] | 7668 [5923, 7900] | 2903 / 3359 | 0 | 82.0 |

### G3. Deriva das âncoras gerenciadas (Parte A − fase 1, mesmos 96 ids de casos quentes, bootstrap pareado)

Reportada, nunca subtraída. Um Δ positivo = o provedor foi mais lento na janela da Parte A.

| âncora | Δ p50 ms [IC 95%] | Δ p95 ms [IC 95%] | casos quentes pareados |
|---|---|---|---|
| E4 Jev (âncora) | 98 [-354, 542] | 1267 [-212, 2999] | 95 |
| E6 Haiku 4.5 (âncora) | -196 [-350, -18] | -1036 [-2006, 209] | 96 |

### G4. Braço gerenciado novo − o seu par local (entre janelas; mesmos 96 ids de casos quentes, bootstrap pareado)

**Ressalva de janela (prereg-v2a §3, obrigatória):** as linhas locais são os blocos lat-* da fase 1, medidos numa janela de tempo diferente da dos blocos da Parte A; o mesmo Mac (M5 Pro 48 GB) no lado local, Bedrock `sa-east-1` (Jev: OpenRouter) chamado desse Mac no lado gerenciado. A deriva é estimada pelas âncoras gerenciadas (Jev, Haiku 4.5) rodadas de novo nas duas janelas; é reportada, nunca subtraída.

| braço gerenciado (Parte A) | par local (fase 1) | Δ p50 ms [IC 95%] | Δ p95 ms [IC 95%] | casos quentes pareados |
|---|---|---|---|---|
| E3c Cohere v4 | E3 qwen3-emb 8B local | 223 [167, 353] | 955 [156, 2216] | 96 |
| E3t Titan v2 | E3 qwen3-emb 8B local | -257 [-271, -240] | -101 [-890, 254] | 96 |
| E10c sonda/Cohere | E10 sonda local | 216 [166, 314] | 474 [-3132, 1128] | 96 |
| E10t sonda/Titan | E10 sonda local | -257 [-268, -244] | -542 [-4255, -6] | 96 |
| E6m Ministral 3 8B | E6b Qwen3-8B local | -8858 [-8939, -7679] | -10399 [-10978, -8689] | 94 |
| E6n Nemotron 9B | E6b Qwen3-8B local | -8639 [-8728, -7491] | -10518 [-10828, -8880] | 96 |

## H. Região que atendeu o Cohere Embed v4 (ESTIMAÇÃO / descritivo)

Configurado: `e3_embedding_cohere` → modelo `global.cohere.embed-v4:0`, região do cliente `sa-east-1`; `e10_classifier_cohere` → modelo `global.cohere.embed-v4:0`, região do cliente `sa-east-1`.

| provedor / modelo atendido (todas as chamadas de estágio do Cohere: runs de teste + latência) | chamadas |
|---|---|
| bedrock / global.cohere.embed-v4:0 | 1796 |

Campos de região no usage gravado: nenhum. **Região que atendeu: não observável.** `global.cohere.embed-v4:0` é um perfil de inferência entre regiões chamado de `sa-east-1`; o InvokeModel do Bedrock não informa a região que atendeu, então a latência do Cohere (§G) inclui qualquer roteamento entre regiões que o Bedrock aplicou (prereg-v2a §9). Titan (`amazon.titan-embed-text-v2:0`) e os dois modelos 8B são ids de modelo da própria região.
