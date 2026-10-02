# Análise primária da Parte A (CONFIRMATÓRIA): família A do prereg-v2a no test-v2

> Tradução pt-BR de [`docs/results/addendum-a/primary.md`](../../../docs/results/addendum-a/primary.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

Gerado por `scripts/analysis/addendum_a.py` (offline, a partir de `results/rescored/`; scorer e0eef1fb0073). Conjunta = acurácia conjunta de roteamento top-1, ITT (uma falha de infra ou de parse conta como erro), 1 rep por braço, pareado por caso sobre os 349 casos do test-v2. Bootstrap pareado por cluster sobre os ids de caso, 10 000 reamostragens, seed 20260930; p = sign-flip no nível do caso (não inferioridade: deslocamento +0.03, unilateral); Holm step-down entre A1-A4 (α 0.05). As referências são as linhas locais congeladas da fase 1, reaproveitadas só para leitura (nenhum modelo local rodou na fase 2).

- **A1 (NI, margem 3 pp):** Conjunta(E6m Ministral 3 8B, Bedrock) − Conjunta(E6b Qwen3-8B local) > −3 pp.
- **A2 (NI, margem 3 pp):** Conjunta(E6n Nemotron Nano 9B v2, Bedrock) − Conjunta(E6b) > −3 pp.
- **A3 (bilateral):** Conjunta(E3c roteador Cohere Embed v4) − Conjunta(E3 qwen3-embedding 8B local).
- **A4 (bilateral):** Conjunta(E3t roteador Titan Text Embeddings v2) − Conjunta(E3).

## Família A: ITT (primária)

| id | run | referência | tipo | n casos | Δ conjunta pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (A1-A4) | rejeita @0.05 | veredito (regra do IC) |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | E6m | E6b | non_inferiority (margem 3 pp) | 349 | 2.3 [-2.0, 6.6] | 34/26 p=0.366 | 0.006799 | 0.0136 | sim | não inferior (limite inferior do IC > -3 pp) |
| A2 | E6n | E6b | non_inferiority (margem 3 pp) | 349 | -2.9 [-7.4, 1.7] | 26/36 p=0.253 | 0.4722 | 0.4722 | não | não inferioridade NÃO demonstrada |
| A3 | E3c | E3 | two_sided | 349 | -19.2 [-24.6, -14.0] | 16/83 p=4.39e-12 | 9.999e-05 | 0.0004 | sim | IC exclui 0 (E3c menor) |
| A4 | E3t | E3 | two_sided | 349 | -17.8 [-23.2, -12.6] | 20/82 p=4.29e-10 | 9.999e-05 | 0.0004 | sim | IC exclui 0 (E3t menor) |

## Família A: casos sem erro nas duas runs (sensibilidade)

| id | run | referência | tipo | n casos | Δ conjunta pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (A1-A4) | rejeita @0.05 | veredito (regra do IC) |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | E6m | E6b | non_inferiority (margem 3 pp) | 347 | 2.9 [-1.4, 7.2] | 34/24 p=0.237 | 0.0028 | 0.005599 | sim | não inferior (limite inferior do IC > -3 pp) |
| A2 | E6n | E6b | non_inferiority (margem 3 pp) | 349 | -2.9 [-7.4, 1.7] | 26/36 p=0.253 | 0.4722 | 0.4722 | não | não inferioridade NÃO demonstrada |
| A3 | E3c | E3 | two_sided | 349 | -19.2 [-24.6, -14.0] | 16/83 p=4.39e-12 | 9.999e-05 | 0.0004 | sim | IC exclui 0 (E3c menor) |
| A4 | E3t | E3 | two_sided | 349 | -17.8 [-23.2, -12.6] | 20/82 p=4.29e-10 | 9.999e-05 | 0.0004 | sim | IC exclui 0 (E3t menor) |

Casos sem erro nas duas runs: A1 347, A2 349, A3 349, A4 349 (de 349).

## Conjunta principal por braço (ITT, IC 95% por bootstrap por cluster)

| braço | run | status | linhas | linhas de erro | conjunta % [IC 95%] |
|---|---|---|---|---|---|
| E6m Ministral 3 8B | v2a-e6m-ministral-canonical-routing-r1 | confirmatório (A1) | 349 | 2 | 82.2 [77.9, 86.2] |
| E6n Nemotron Nano 9B v2 | v2a-e6n-nemotron-canonical-routing-r1 | confirmatório (A2) | 349 | 0 | 77.1 [72.5, 81.4] |
| E6b Qwen3-8B local (fase 1) | v2-e6b-qwen-canonical-routing-r1 | reference (fase 1, reaproveitado) | 349 | 0 | 79.9 [75.6, 84.0] |
| E3c roteador Cohere Embed v4 | v2a-e3c-cohere-routing-r1 | confirmatório (A3) | 349 | 0 | 54.4 [49.3, 59.6] |
| E3t roteador Titan v2 | v2a-e3t-titan-routing-r1 | confirmatório (A4) | 349 | 0 | 55.9 [50.4, 61.0] |
| E3 qwen3-embedding 8B local (fase 1) | v2-e3-embedding-routing-r1 | reference (fase 1, reaproveitado) | 349 | 0 | 73.6 [68.8, 78.2] |

## Resumo das decisões

| id | contraste | Δ pp [IC 95%] | p Holm | leitura |
|---|---|---|---|---|
| A1 | E6m − E6b | 2.3 [-2.0, 6.6] | 0.0136 | não inferioridade DEMONSTRADA pela regra do IC; o sign-flip com Holm rejeita Δ ≤ −3 pp |
| A2 | E6n − E6b | -2.9 [-7.4, 1.7] | 0.4722 | não inferioridade NÃO demonstrada pela regra do IC; o sign-flip com Holm não rejeita Δ ≤ −3 pp |
| A3 | E3c − E3 | -19.2 [-24.6, -14.0] | 0.0004 | diferença: IC exclui 0 (E3c menor); Holm rejeita Δ = 0 |
| A4 | E3t − E3 | -17.8 [-23.2, -12.6] | 0.0004 | diferença: IC exclui 0 (E3t menor); Holm rejeita Δ = 0 |

## Regras de leitura (pré-registradas)

- A1/A2: não inferior sse o limite inferior do IC 95% pareado bilateral de Δ (= unilateral 97.5%) fica acima de −3 pp (regra do prereg-v1, herdada pelo prereg-v2a §0). O p sign-flip ajustado por Holm testa H0: Δ ≤ −3 pp. Os dois são mostrados; quando discordam, a regra do IC é a decisão pré-registrada e a coluna de Holm é o teste com controle de multiplicidade.
- A3/A4: bilateral; afirmação direcional só se o IC excluir 0. p sign-flip ajustado por Holm de H0: Δ = 0.
- ITT: uma falha de parse é uma linha de erro e conta como errada (o E6m tem 2 dessas linhas; estimation.md §E). A sensibilidade sem erros restringe cada contraste aos casos sem erro nas duas runs dele.
- Expectativa no dev (não é teste; docs/tuning-effort-l.md §A): E6m 79.5, E6n 78.1 vs E6b 82.2 (CV no dev); E3c 59.6, E3t 60.3 vs E3 77.5 (CV aninhada).

## Proveniência (verificada em toda linha: prereg-v2a §1, §6, §8)

Toda linha de toda run abaixo carrega catalog_hash 128584617807, prompt_hash c61ad0a7b7f8, scorer_hash e0eef1fb0073, dataset sha256 6637c479…, e o config_hash congelado no prereg-v2a §1 (Parte A) ou em `config/study_manifest.yaml` (fase 1); o sha256 do manifesto do adendo é 177e374a…; toda run da Parte A está COMPLETE em results/phase2a/run-manifest.log; os arquivos reaproveitados da fase 1 batem com os prefixos de sha256 do §1. O script para em qualquer divergência.

| run | origem | linhas | config_hash | status / verificação | linhas de erro (ITT) |
|---|---|---|---|---|---|
| v2a-e3c-cohere-routing-r1 | Parte A | 349 | 56f1708d24de | COMPLETE | 0 |
| v2a-e3t-titan-routing-r1 | Parte A | 349 | 73f81417a487 | COMPLETE | 0 |
| v2a-e10c-cohere-routing-r1 | Parte A | 349 | fc05bbd1c5aa | COMPLETE | 0 |
| v2a-e10t-titan-routing-r1 | Parte A | 349 | 70374caa4b59 | COMPLETE | 0 |
| v2a-e6m-ministral-canonical-routing-r1 | Parte A | 349 | 0d8fbee553f3 | COMPLETE | 2 |
| v2a-e6n-nemotron-canonical-routing-r1 | Parte A | 349 | efb00ce5b9f8 | COMPLETE | 0 |
| v2a-e6m-ministral-canonical-repeat50 | Parte A | 100 | 0d8fbee553f3 | COMPLETE | 0 |
| v2a-e6n-nemotron-canonical-repeat50 | Parte A | 100 | efb00ce5b9f8 | COMPLETE | 0 |
| lat-a-* (32 blocos) | Parte A | 800 | conforme §1 | COMPLETE (todas) | ver estimation.md |
| v2-e6b-qwen-canonical-routing-r1 | fase 1 (reaproveitado) | 349 | 903a4a1e56d3 | sha256 6a99aab7fc6b116d… ok | 0 |
| v2-e3-embedding-routing-r1 | fase 1 (reaproveitado) | 349 | 1899b6f414a5 | sha256 4c13be42cda91614… ok | 0 |
| v2-e10-classifier-routing-r1 | fase 1 (reaproveitado) | 349 | 616af886b783 | sha256 b14c2893e454ce80… ok | 0 |
| lat-{qwen,embedding,classifier,jev,haiku}-b1..4 | fase 1 (reaproveitado) | 500 | conforme study_manifest | COMPLETE (todas) | ver estimation.md |
