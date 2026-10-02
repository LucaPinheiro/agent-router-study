# Calibração de thresholds de cascade: freeze-dev-shadow-r1.jsonl

- fonte: freeze-dev-shadow-r1.jsonl (151 linhas), dataset dataset_dev.jsonl 112fc7f0791e, scorer e0eef1fb0073, git da run ['b76b3b1-dirty.42b16ddf']
- grid 0.50..0.99 (50 valores) por etapa não final; budget US$ 0.0029875/caso; CV de 5 folds estratificada por categoria sobre os ids de caso, seed 0; regra (b) com suporte mínimo de 5 casos aceitos
- intenção de tratar (ITT): toda linha conta; uma etapa de routing que falha (erro ou falha de parse) é ERRADA, nunca uma abstenção, de modo que um threshold não pode vencer roteando casos com falha para um erro; joint %: uma etapa de tool que não pode ser reproduzida (a skill simulada difere da registrada) conta 0 (limite inferior); US$/1k custo de routing sobre as linhas cobertas; ICs de 95%: cluster bootstrap sobre os ids de caso (`eval/stats.py`, seed fixa)
- 'dev' = ajustado e avaliado em todas as linhas de dev (otimista); 'CV held-out' = reajustado em k-1 folds, avaliado no fold held-out, agregado
- confidências como registradas: 564/564 decisões de regex/BM25 trazem `usage.raw_confidence` (0 = a run é anterior aos mapas de calibração: seus thresholds estão na escala bruta; refaça a shadow run com a config atual antes de aplicá-los)

## e7_regex_jev

skill: regex -> jev | tool: jev | 50 combos | 151 linhas (0 excluídas por erro em alguma etapa) | avaliador rápido == simulate_rows em 11 pontos

| método | thresholds de skill | thresholds de tool | joint % dev | US$/1k dev | joint % CV held-out | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.90 | - | 79.5 [72.8, 85.4] | 0.8922 [0.7571, 1.0396] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) joint máx. s.a. budget | regex=0.81 | - | 79.5 [72.8, 85.4] | 0.8626 [0.7270, 1.0076] | 78.8 [72.2, 85.4] | 0.8647 [0.7277, 1.0138] | regex=0.81 / - x3; regex=0.88 / - x1; regex=0.83 / - x1 |
| (b) regra de precisão | regex=0.62 | - | 76.2 [69.5, 82.8] | 0.8185 [0.6830, 0.9622] | 76.2 [68.9, 82.8] | 0.8180 [0.6825, 0.9676] | regex=0.50 / - x2; regex=0.70 / - x2; regex=0.62 / - x1 |

Regra (b) em todas as linhas de dev:

| estágio | etapa | alvo = precisão da próxima etapa | threshold | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |

Referências em dev (todas as linhas, sem ajuste):

| referência | joint % [IC 95%] | US$/1k routing [IC 95%] |
|---|---|---|
| always-last (só o router final) | 76.8 [69.5, 83.4] | 0.9385 [0.8008, 1.0824] |
| always-first (toda etapa aceita qualquer escolha) | 75.5 [68.2, 82.1] | 0.8188 [0.6822, 0.9675] |
| oracle (melhor etapa de parada por linha) | 80.8 [74.2, 86.8] | 0.5663 [0.4705, 0.6735] |
| deferral aleatório nas taxas de (a) joint máx. s.a. budget (200 sorteios, média) | 75.9 | 0.8537 |
| deferral aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 75.5 | 0.8205 |

Fronteira de Pareto em dev (3 pontos; pareto.csv):

| thresholds de skill | thresholds de tool | joint % | joint cob. % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.63 | - | 76.2 | 77.7 | 0.8185 | 151 | 0 | 3 |
| regex=0.74 | - | 78.8 | 79.3 | 0.8414 | 151 | 0 | 1 |
| regex=0.81 | - | 79.5 | 80.0 | 0.8626 | 151 | 0 | 1 |

## e8_regex_llm

skill: regex -> llm | tool: llm | 50 combos | 151 linhas (0 excluídas por erro em alguma etapa) | avaliador rápido == simulate_rows em 12 pontos

| método | thresholds de skill | thresholds de tool | joint % dev | US$/1k dev | joint % CV held-out | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.90 | - | 78.1 [71.5, 84.8] | 5.2076 [4.8329, 5.6168] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) joint máx. s.a. budget | inviável | | | | | | |
| (b) regra de precisão | regex=0.62 | - | 74.8 [68.2, 81.5] | 4.6778 [4.3297, 5.0525] | 74.2 [66.9, 80.8] | 4.6793 [4.3342, 5.0586] | regex=0.50 / - x2; regex=0.62 / - x2; regex=0.70 / - x1 |

Regra (b) em todas as linhas de dev:

| estágio | etapa | alvo = precisão da próxima etapa | threshold | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |

Referências em dev (todas as linhas, sem ajuste):

| referência | joint % [IC 95%] | US$/1k routing [IC 95%] |
|---|---|---|
| always-last (só o router final) | 76.8 [69.5, 83.4] | 5.9150 [5.5388, 6.3098] |
| always-first (toda etapa aceita qualquer escolha) | 74.2 [66.9, 80.8] | 4.6557 [4.3083, 5.0338] |
| oracle (melhor etapa de parada por linha) | 80.1 [73.5, 86.1] | 3.7123 [3.3645, 4.0834] |
| deferral aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 74.2 | 4.6739 |

Fronteira de Pareto em dev (5 pontos; pareto.csv):

| thresholds de skill | thresholds de tool | joint % | joint cob. % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.50 | - | 74.2 | 75.7 | 4.6557 | 151 | 0 | 3 |
| regex=0.63 | - | 74.8 | 76.4 | 4.6778 | 151 | 0 | 3 |
| regex=0.74 | - | 77.5 | 78.0 | 4.7724 | 151 | 0 | 1 |
| regex=0.81 | - | 78.1 | 78.7 | 5.0228 | 151 | 0 | 1 |
| regex=0.88 | - | 78.8 | 79.3 | 5.1690 | 151 | 0 | 1 |

## e9_regex_jev_llm

skill: regex -> jev -> llm | tool: jev -> llm | 125000 combos | 151 linhas (0 excluídas por erro em alguma etapa) | avaliador rápido == simulate_rows em 12 pontos

| método | thresholds de skill | thresholds de tool | joint % dev | US$/1k dev | joint % CV held-out | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.90, jev=0.75 | jev=0.70 | 80.1 [73.5, 86.1] | 2.3486 [1.8473, 2.8776] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) joint máx. s.a. budget | regex=0.88, jev=0.76 | jev=0.50 | 80.1 [73.5, 86.1] | 1.2046 [0.9512, 1.4858] | 77.5 [70.9, 84.1] | 1.2761 [0.9932, 1.5996] | regex=0.81, jev=0.73 / jev=0.50 x1; regex=0.88, jev=0.73 / jev=0.65 x1; regex=0.88, jev=0.76 / jev=0.50 x3 |
| (b) regra de precisão | regex=0.62, jev=0.50 | jev=0.50 | 76.2 [69.5, 82.8] | 0.9421 [0.7316, 1.1879] | 76.2 [68.9, 82.8] | 0.9416 [0.7344, 1.1868] | regex=0.50, jev=0.50 / jev=0.50 x2; regex=0.70, jev=0.50 / jev=0.50 x2; regex=0.62, jev=0.50 / jev=0.50 x1 |

Regra (b) em todas as linhas de dev:

| estágio | etapa | alvo = precisão da próxima etapa | threshold | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |
| skill | jev | 91.4% | 0.50 | 94.4% | 18 |
| tool | jev | 83.2% | 0.50 | 86.3% | 139 |

Referências em dev (todas as linhas, sem ajuste):

| referência | joint % [IC 95%] | US$/1k routing [IC 95%] |
|---|---|---|
| always-last (só o router final) | 76.8 [69.5, 83.4] | 6.8631 [6.4352, 7.3162] |
| always-first (toda etapa aceita qualquer escolha) | 75.5 [68.2, 82.1] | 0.8188 [0.6822, 0.9675] |
| oracle (melhor etapa de parada por linha) | 83.4 [77.5, 89.4] | 0.8758 [0.7410, 1.0227] |
| deferral aleatório nas taxas de (a) joint máx. s.a. budget (200 sorteios, média) | 76.1 | 1.1133 |
| deferral aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 75.5 | 0.9419 |

Fronteira de Pareto em dev (4 pontos; pareto.csv):

| thresholds de skill | thresholds de tool | joint % | joint cob. % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.63, jev=0.73 | jev=0.50 | 76.2 | 77.7 | 0.9421 | 151 | 0 | 3 |
| regex=0.74, jev=0.73 | jev=0.50 | 78.8 | 79.3 | 0.9607 | 151 | 0 | 1 |
| regex=0.81, jev=0.73 | jev=0.50 | 79.5 | 80.0 | 0.9811 | 151 | 0 | 1 |
| regex=0.88, jev=0.76 | jev=0.50 | 80.1 | 80.7 | 1.2046 | 151 | 0 | 1 |

## e12_hybrid_jev_llm

skill: hybrid -> jev -> llm | tool: jev -> llm | 125000 combos | 151 linhas (0 excluídas por erro em alguma etapa) | avaliador rápido == simulate_rows em 11 pontos

| método | thresholds de skill | thresholds de tool | joint % dev | US$/1k dev | joint % CV held-out | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | hybrid=0.90, jev=0.75 | jev=0.70 | 79.5 [72.8, 85.4] | 2.1950 [1.7153, 2.7108] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) joint máx. s.a. budget | hybrid=0.83, jev=0.77 | jev=0.50 | 80.1 [73.5, 86.1] | 1.0209 [0.7912, 1.2866] | 78.1 [71.5, 84.8] | 1.1910 [0.9230, 1.4884] | hybrid=0.81, jev=0.73 / jev=0.50 x1; hybrid=0.83, jev=0.77 / jev=0.65 x1; hybrid=0.83, jev=0.77 / jev=0.50 x2; hybrid=0.83, jev=0.80 / jev=0.50 x1 |
| (b) regra de precisão | hybrid=0.50, jev=never | jev=0.50 | 77.5 [70.9, 84.1] | 0.9075 [0.7010, 1.1565] | 77.5 [70.9, 84.1] | 0.9075 [0.7010, 1.1565] | hybrid=0.50, jev=never / jev=0.50 x5 |

Regra (b) em todas as linhas de dev:

| estágio | etapa | alvo = precisão da próxima etapa | threshold | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | hybrid | 91.4% | 0.50 | 93.4% | 151 |
| skill | jev | 91.4% | never (remover etapa) | - | 0 |
| tool | jev | 83.2% | 0.50 | 86.3% | 139 |

Referências em dev (todas as linhas, sem ajuste):

| referência | joint % [IC 95%] | US$/1k routing [IC 95%] |
|---|---|---|
| always-last (só o router final) | 76.8 [69.5, 83.4] | 6.8631 [6.4352, 7.3162] |
| always-first (toda etapa aceita qualquer escolha) | 77.5 [70.9, 84.1] | 0.7865 [0.6522, 0.9351] |
| oracle (melhor etapa de parada por linha) | 83.4 [77.5, 89.4] | 0.8254 [0.6921, 0.9697] |
| deferral aleatório nas taxas de (a) joint máx. s.a. budget (200 sorteios, média) | 77.4 | 0.9812 |
| deferral aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 77.5 | 0.9060 |

Fronteira de Pareto em dev (3 pontos; pareto.csv):

| thresholds de skill | thresholds de tool | joint % | joint cob. % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| hybrid=0.79, jev=0.73 | jev=0.50 | 78.8 | 79.9 | 0.9046 | 151 | 0 | 2 |
| hybrid=0.81, jev=0.73 | jev=0.50 | 79.5 | 80.5 | 0.9073 | 151 | 0 | 2 |
| hybrid=0.83, jev=0.77 | jev=0.50 | 80.1 | 81.2 | 1.0209 | 151 | 0 | 2 |
## Fallback do E8 (budget inviável): Calibração de thresholds de cascade: freeze-dev-shadow-r1.jsonl

- fonte: freeze-dev-shadow-r1.jsonl (151 linhas), dataset dataset_dev.jsonl 112fc7f0791e, scorer e0eef1fb0073, git da run ['b76b3b1-dirty.42b16ddf']
- grid 0.50..0.99 (50 valores) por etapa não final; sem budget (acurácia joint máxima); CV de 5 folds estratificada por categoria sobre os ids de caso, seed 0; regra (b) com suporte mínimo de 5 casos aceitos
- intenção de tratar (ITT): toda linha conta; uma etapa de routing que falha (erro ou falha de parse) é ERRADA, nunca uma abstenção, de modo que um threshold não pode vencer roteando casos com falha para um erro; joint %: uma etapa de tool que não pode ser reproduzida (a skill simulada difere da registrada) conta 0 (limite inferior); US$/1k custo de routing sobre as linhas cobertas; ICs de 95%: cluster bootstrap sobre os ids de caso (`eval/stats.py`, seed fixa)
- 'dev' = ajustado e avaliado em todas as linhas de dev (otimista); 'CV held-out' = reajustado em k-1 folds, avaliado no fold held-out, agregado
- confidências como registradas: 564/564 decisões de regex/BM25 trazem `usage.raw_confidence` (0 = a run é anterior aos mapas de calibração: seus thresholds estão na escala bruta; refaça a shadow run com a config atual antes de aplicá-los)

## e8_regex_llm

skill: regex -> llm | tool: llm | 50 combos | 151 linhas (0 excluídas por erro em alguma etapa) | avaliador rápido == simulate_rows em 13 pontos

| método | thresholds de skill | thresholds de tool | joint % dev | US$/1k dev | joint % CV held-out | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.90 | - | 78.1 [71.5, 84.8] | 5.2076 [4.8329, 5.6168] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) joint máx. s.a. budget | regex=0.88 | - | 78.8 [72.2, 85.4] | 5.1690 [4.7919, 5.5812] | 78.1 [71.5, 84.8] | 5.1382 [4.7505, 5.5640] | regex=0.81 / - x1; regex=0.88 / - x4 |
| (b) regra de precisão | regex=0.62 | - | 74.8 [68.2, 81.5] | 4.6778 [4.3297, 5.0525] | 74.2 [66.9, 80.8] | 4.6793 [4.3342, 5.0586] | regex=0.50 / - x2; regex=0.62 / - x2; regex=0.70 / - x1 |

Regra (b) em todas as linhas de dev:

| estágio | etapa | alvo = precisão da próxima etapa | threshold | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |

Referências em dev (todas as linhas, sem ajuste):

| referência | joint % [IC 95%] | US$/1k routing [IC 95%] |
|---|---|---|
| always-last (só o router final) | 76.8 [69.5, 83.4] | 5.9150 [5.5388, 6.3098] |
| always-first (toda etapa aceita qualquer escolha) | 74.2 [66.9, 80.8] | 4.6557 [4.3083, 5.0338] |
| oracle (melhor etapa de parada por linha) | 80.1 [73.5, 86.1] | 3.7123 [3.3645, 4.0834] |
| deferral aleatório nas taxas de (a) joint máx. s.a. budget (200 sorteios, média) | 75.2 | 5.1449 |
| deferral aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 74.2 | 4.6739 |

Fronteira de Pareto em dev (5 pontos; pareto.csv):

| thresholds de skill | thresholds de tool | joint % | joint cob. % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.50 | - | 74.2 | 75.7 | 4.6557 | 151 | 0 | 3 |
| regex=0.63 | - | 74.8 | 76.4 | 4.6778 | 151 | 0 | 3 |
| regex=0.74 | - | 77.5 | 78.0 | 4.7724 | 151 | 0 | 1 |
| regex=0.81 | - | 78.1 | 78.7 | 5.0228 | 151 | 0 | 1 |
| regex=0.88 | - | 78.8 | 79.3 | 5.1690 | 151 | 0 | 1 |
