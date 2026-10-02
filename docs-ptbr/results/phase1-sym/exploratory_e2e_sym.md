# e2e da fase 1 com o scorer simétrico (EXPLORATÓRIO)

> Tradução pt-BR de [`docs/results/phase1-sym/exploratory_e2e_sym.md`](../../../docs/results/phase1-sym/exploratory_e2e_sym.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

**Todo número desta página é EXPLORATÓRIO.** O scorer simétrico (`src/routing_study/eval/scorers_sym.py`, prereg-v2 §4) foi desenhado depois de ver os resultados da fase 1 no test-v2 (o achado das mesmas chamadas, 22/40, em `exploratory_e2e.md` §2). Ele é reaplicado aqui OFFLINE às linhas gravadas da fase 1, a custo zero de API. O veredito confirmatório da fase 1 (prereg-v1 H3, scorer legacy `e0eef1fb0073`) **não** muda: E0 > E9.

O que muda: o scorer legacy tira a skill do e2e do rótulo do ROTEADOR nas runs roteadas e do comportamento (`load_skill`) no E0. O scorer simétrico a tira do comportamento nos dois braços: a skill da primeira tool de negócio ligada a uma skill que o servidor executou; sem chamada, a skill da tool creditada por uma clarificação (inferida da pergunta, nunca da tool do roteador); só escalonamento ou abstenção do host = `__abstain__`; só chamadas globais = `__global__`; nenhuma ação = `__abstain__`. Ele nunca lê `native`, a skill/tool do roteador nem `resolved_by`. Todo o resto (args, conclusão, recuperação, decomposição) é o código legacy.

Estatística: idêntica à de primary.md. Unidade = caso (repetições tiradas a média primeiro); bootstrap pareado por cluster sobre os ids de caso, 10000 reamostragens, seed 20260930; McNemar exato sobre as maiorias por caso; p sign-flip bilateral, **sem ajuste**. Intenção de tratar (nenhuma run e2e teve linha de erro). Os números legacy são lidos de `results/rescored/`, os simétricos de `results/rescored-sym/`, ambos reescorados a partir dos mesmos arquivos brutos (sha256 conferido).

## 1. H3 (E9 − E0) com os dois scorers

| scorer | E9 e2e_success % [IC 95%] | E0 e2e_success % [IC 95%] | Δ E9 − E0 pp [IC 95%] | McNemar só E9 / só E0 | p sign-flip (sem ajuste) |
|---|---|---|---|---|---|
| legacy (pré-registrado, confirmatório na fase 1) | 45.8 [40.4, 51.0] | 55.6 [50.1, 60.7] | **-9.7 [-13.5, -6.0]** | 6 / 40 (p=3.1e-07) | 9.999e-05 |
| simétrico (EXPLORATÓRIO) | 53.0 [47.6, 58.2] | 56.2 [50.7, 61.3] | **-3.2 [-6.0, -0.3]** | 7 / 18 (p=0.0433) | 0.0425 |

O legacy reproduz primary.md exatamente (-9.7 [-13.5, -6.0]). Com o scorer simétrico, o IC exclui 0.

## 2. Todos os braços e2e

test-v2, 349 casos, 1 rep cada.

| braço | n | e2e legacy % [IC] | e2e sym % [IC] | sym − legacy pp | linhas alteradas | sym: 1ª chamada | sym: + clarificação | sym: + recuperação | sym skill_correct % |
|---|---|---|---|---|---|---|---|---|---|
| E0 nativo (sem roteador) | 349 | 55.6 [50.1, 60.7] | **56.2 [50.7, 61.3]** | +0.6 | +2 / −0 | 53.6 | 1.7 | 0.9 | 82.2 |
| E1 regex | 349 | 34.7 [29.8, 39.5] | **41.5 [36.4, 46.7]** | +6.9 | +24 / −0 | 40.7 | 0.6 | 0.3 | 62.5 |
| E5 Sonnet 5 | 349 | 50.7 [45.3, 55.9] | **56.2 [50.7, 61.3]** | +5.4 | +19 / −0 | 55.0 | 1.1 | 0.0 | 81.1 |
| E6b Qwen3-8B local | 349 | 46.4 [41.3, 51.6] | **55.0 [49.6, 60.2]** | +8.6 | +30 / −0 | 53.3 | 1.4 | 0.3 | 79.9 |
| E7 regex->Jev | 349 | 45.0 [39.8, 50.1] | **54.2 [48.7, 59.3]** | +9.2 | +32 / −0 | 52.1 | 1.7 | 0.3 | 80.8 |
| E9 regex->Jev->Sonnet | 349 | 45.8 [40.4, 51.0] | **53.0 [47.6, 58.2]** | +7.2 | +25 / −0 | 51.9 | 1.1 | 0.0 | 79.7 |
| E11 híbrido | 349 | 44.4 [39.3, 49.6] | **52.1 [46.7, 57.3]** | +7.7 | +27 / −0 | 50.7 | 1.4 | 0.0 | 76.2 |
| E9 todas as tools da skill (D-002) | 349 | 48.1 [43.0, 53.3] | **55.0 [49.6, 60.2]** | +6.9 | +24 / −0 | 54.4 | 0.6 | 0.0 | 80.8 |
| E7 todas as tools da skill (D-002) | 349 | 44.7 [39.5, 49.9] | **53.0 [47.9, 58.2]** | +8.3 | +29 / −0 | 51.3 | 1.4 | 0.3 | 79.4 |

`linhas alteradas` = turnos cujo veredito e2e difere entre os dois scorers: +falha→sucesso / −sucesso→falha. Em todo braço, o scorer simétrico só transforma falhas em sucessos, nunca o contrário.

## 3. Contrastes (pareados, sem ajuste, EXPLORATÓRIOS)

|  | contraste | Δ legacy pp [IC 95%] | legacy só-run / só-ref | Δ sym pp [IC 95%] | sym só-run / só-ref | IC sym |
|---|---|---|---|---|---|---|
| H3 | E9 − E0 | -9.7 [-13.5, -6.0] | 6 / 40 | -3.2 [-6.0, -0.3] | 7 / 18 | exclui 0 |
|  | E1 − E0 | -20.9 [-25.8, -16.0] | 8 / 81 | -14.6 [-19.2, -10.0] | 10 / 61 | exclui 0 |
|  | E5 − E0 | -4.9 [-8.3, -1.4] | 11 / 28 | 0.0 [-2.6, 2.6] | 11 / 11 | inclui 0 |
|  | E6b − E0 | -9.2 [-13.2, -5.2] | 12 / 44 | -1.1 [-4.3, 2.0] | 13 / 17 | inclui 0 |
|  | E7 − E0 | -10.6 [-14.6, -6.9] | 8 / 45 | -2.0 [-4.9, 0.9] | 10 / 17 | inclui 0 |
|  | E11 − E0 | -11.2 [-15.5, -6.9] | 10 / 49 | -4.0 [-7.4, -0.6] | 11 / 25 | exclui 0 |
| D-002 | E9-full − E0 | -7.4 [-11.5, -3.4] | 13 / 39 | -1.1 [-4.3, 2.0] | 13 / 17 | inclui 0 |
| D-002 | E7-full − E0 | -10.9 [-14.9, -6.9] | 8 / 46 | -3.2 [-6.0, -0.3] | 8 / 19 | exclui 0 |
| D-002 | E9-full − E9 | 2.3 [0.0, 4.6] | 12 / 4 | 2.0 [-0.3, 4.3] | 12 / 5 | inclui 0 |
| D-002 | E7-full − E7 | -0.3 [-2.3, 2.0] | 7 / 8 | -1.1 [-3.4, 1.1] | 6 / 10 | inclui 0 |

## 4. Mesmas chamadas, veredito diferente

Casos discordantes (sucesso e2e em exatamente uma das duas runs), e quantos deles têm a MESMA sequência de chamadas de negócio executadas (sem `load_skill`) nas duas runs. A fase 1 reportou 22 dos 40 casos só-E0 de E9 − E0 como classes A1 + A2 (mesmas chamadas E rótulo de skill do roteador não aceito; `exploratory_e2e.md` §2). A contagem legacy aqui é um pouco maior porque também inclui casos com as mesmas chamadas que falharam em args ou conclusão. Uma discordância com as mesmas chamadas que sobra no scorer simétrico vem dos args ou da resposta (por exemplo, uma clarificação), não do rótulo de skill.

| par | legacy: só-E0 com as mesmas chamadas | legacy: todos os discordantes com as mesmas chamadas | sym: só-E0 com as mesmas chamadas | sym: todos os discordantes com as mesmas chamadas |
|---|---|---|---|---|
| E9 vs E0 | 24 / 40 | 26 / 46 | 2 / 18 | 4 / 25 |
| E1 vs E0 | 19 / 81 | 24 / 89 | 3 / 61 | 8 / 71 |
| E5 vs E0 | 19 / 28 | 25 / 39 | 2 / 11 | 8 / 22 |
| E6b vs E0 | 26 / 44 | 32 / 56 | 1 / 17 | 7 / 30 |
| E7 vs E0 | 26 / 45 | 31 / 53 | 0 / 17 | 5 / 27 |
| E11 vs E0 | 23 / 49 | 29 / 59 | 1 / 25 | 7 / 36 |
| E9-full vs E0 | 24 / 39 | 30 / 52 | 2 / 17 | 8 / 30 |
| E7-full vs E0 | 23 / 46 | 28 / 54 | 0 / 19 | 5 / 27 |

## 5. Runs de variância do executor (rep2 em 60 casos)

Mesmas decisões de roteamento (cache), executor reamostrado. `flips` = casos (de 60) cujo veredito e2e difere entre a rep 1 (run principal) e a rep 2.

| run | e2e rep2 legacy % | flips legacy | e2e rep2 sym % | flips sym |
|---|---|---|---|---|
| E0 rep2-60 | 53.3 | 3/60 | 55.0 | 3/60 |
| E9 rep2-60 | 43.3 | 1/60 | 50.0 | 2/60 |

## 6. Proveniência

Hash do scorer simétrico: 5ad0f65296e4. Hash do scorer legacy: e0eef1fb0073 (sem mudança, verificado por `tests/test_phase1_hashes.py`). Comando de reescore: `uv run study rescore results/<run>.jsonl --scorer sym`.

| run | linhas | sha256 bruto | scorer legacy | scorer sym |
|---|---|---|---|---|
| v2-e0-native-e2e-r1 | 349 | 296f62b8eb75 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e1-regex-e2e-r1 | 349 | b97aeba66155 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e5-sonnet-canonical-e2e-r1 | 349 | b1072e852da1 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e6b-qwen-canonical-e2e-r1 | 349 | a4e70bc51a75 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e7-tuned-e2e-r1 | 349 | 6a18ec1afcea | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e9-tuned-e2e-r1 | 349 | d25dc21ced7d | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e11-hybrid-e2e-r1 | 349 | ea59ebcd04a6 | e0eef1fb0073 | 5ad0f65296e4 |
| x-e9-fullskill-e2e-r1 | 349 | 2fec42caaa61 | e0eef1fb0073 | 5ad0f65296e4 |
| x-e7-fullskill-e2e-r1 | 349 | a9242cc6e4f6 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e0-native-e2e-rep2-60 | 60 | 626253131ee1 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e9-tuned-e2e-rep2-60 | 60 | db4382843c3d | e0eef1fb0073 | 5ad0f65296e4 |

Ressalvas: post hoc, mesmo split de teste da análise confirmatória, uma amostra do executor por caso (as runs rep2 acima limitam o ruído do executor). Estes números alimentam as suposições de tamanho de efeito e de MDE do H1-L no prereg-v2. Não são um resultado da fase 1.
