# Calibração de limiares de cascata: freeze-dev-l-shadow-r1.jsonl

> Tradução pt-BR de [`docs/results/phase2-dev-l/cascade-thresholds-dev-l.md`](../../../docs/results/phase2-dev-l/cascade-thresholds-dev-l.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

- origem: freeze-dev-l-shadow-r1.jsonl (150 linhas), dataset dataset_dev_l.jsonl b02b3722f5c4, scorer e0eef1fb0073, run git ['5d7ffc6']
- grade 0.50..0.99 (50 valores) por passo que não é o último; orçamento US$ 0.003761/caso; CV de 5 folds estratificada por categoria sobre os ids de caso, seed 0; regra (b) com suporte mínimo de 5 casos aceitos
- intenção de tratar: toda linha conta; um estágio de roteamento que falhou (erro ou falha de parse) é ERRADO, nunca uma abstenção, então um limiar não pode ganhar mandando casos que falham para um erro; conjunta %: um estágio de tool que não pode ser reproduzido (skill simulada diferente da gravada) conta 0 (limite inferior); custo de roteamento US$/1k sobre as linhas cobertas; ICs 95%: bootstrap por cluster sobre os ids de caso (`eval/stats.py`, seed fixa)
- 'dev' = ajustado e pontuado em todas as linhas do dev (otimista); 'CV held-out' = reajustado em k-1 folds, pontuado no fold separado, reunido
- confianças como gravadas: 582/582 decisões de regex/BM25 carregam `usage.raw_confidence` (0 = a run é anterior aos mapas de calibração: os seus limiares estão na escala bruta; rode de novo a run shadow com a config atual antes de aplicá-los)

## e7_regex_jev_l

skill: regex -> jev | tool: jev | 50 combinações | 150 linhas (0 excluídas por erro em algum passo) | avaliador rápido == simulate_rows em 15 pontos

| método | limiares de skill | limiares de tool | conjunta dev % | US$/1k dev | conjunta CV held-out % | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.81 | - | 84.0 [78.0, 89.3] | 1.0077 [0.8434, 1.2052] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) conjunta máxima sujeita ao orçamento | regex=0.88 | - | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | 86.0 [80.0, 91.3] | 1.0390 [0.8746, 1.2340] | regex=0.89 / - x1; regex=0.88 / - x4 |
| (b) regra de precisão | regex=0.88 | - | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | 85.3 [79.3, 90.7] | 1.0405 [0.8728, 1.2390] | regex=0.88 / - x1; regex=0.89 / - x2; regex=0.67 / - x1; regex=0.81 / - x1 |

Regra (b) em todas as linhas do dev:

| estágio | passo | alvo = precisão do passo seguinte | limiar | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 92.7% | 0.88 | 93.3% | 105 |

Referências no dev (todas as linhas, sem ajuste):

| referência | conjunta % [IC 95%] | US$/1k roteamento [IC 95%] |
|---|---|---|
| sempre o último (só o roteador final) | 81.3 [74.7, 87.3] | 1.2966 [1.0890, 1.5400] |
| sempre o primeiro (todo passo aceita qualquer escolha) | 80.0 [73.3, 86.0] | 0.9224 [0.7618, 1.1171] |
| oráculo (melhor passo de parada por linha) | 88.0 [82.7, 92.7] | 0.8344 [0.6698, 1.0364] |
| adiamento aleatório nas taxas de (a) conjunta máxima sujeita ao orçamento (200 sorteios, média) | 80.3 | 1.0214 |
| adiamento aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 80.3 | 1.0214 |

Fronteira de Pareto no dev (7 pontos; pareto.csv):

| limiares de skill | limiares de tool | conjunta % | cob. conjunta % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.65 | - | 80.0 | 83.3 | 0.9206 | 150 | 0 | 6 |
| regex=0.69 | - | 80.7 | 84.0 | 0.9212 | 150 | 0 | 6 |
| regex=0.72 | - | 81.3 | 84.7 | 0.9387 | 150 | 0 | 6 |
| regex=0.80 | - | 82.0 | 84.8 | 0.9743 | 150 | 0 | 5 |
| regex=0.83 | - | 84.0 | 85.1 | 1.0077 | 150 | 0 | 2 |
| regex=0.87 | - | 85.3 | 85.9 | 1.0120 | 150 | 0 | 1 |
| regex=0.88 | - | 86.7 | 86.7 | 1.0337 | 150 | 0 | 0 |

## e8_regex_llm_l

skill: regex -> llm | tool: llm | 50 combinações | 150 linhas (0 excluídas por erro em algum passo) | avaliador rápido == simulate_rows em 11 pontos

| método | limiares de skill | limiares de tool | conjunta dev % | US$/1k dev | conjunta CV held-out % | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) conjunta máxima sujeita ao orçamento | infeasible | | | | | | |
| (b) regra de precisão | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | 82.7 [76.0, 88.7] | 6.4198 [5.9044, 6.9834] | regex=0.89 / - x3; regex=0.84 / - x1; regex=0.81 / - x1 |

Regra (b) em todas as linhas do dev:

| estágio | passo | alvo = precisão do passo seguinte | limiar | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 92.7% | 0.88 | 93.3% | 105 |

Referências no dev (todas as linhas, sem ajuste):

| referência | conjunta % [IC 95%] | US$/1k roteamento [IC 95%] |
|---|---|---|
| sempre o último (só o roteador final) | 80.0 [73.3, 86.0] | 7.5350 [6.9791, 8.1182] |
| sempre o primeiro (todo passo aceita qualquer escolha) | 79.3 [72.7, 85.3] | 6.1567 [5.5918, 6.7548] |
| oráculo (melhor passo de parada por linha) | 85.3 [79.3, 90.7] | 5.2436 [4.6846, 5.8456] |
| adiamento aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 79.5 | 6.5146 |

Fronteira de Pareto no dev (4 pontos; pareto.csv):

| limiares de skill | limiares de tool | conjunta % | cob. conjunta % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.58 | - | 79.3 | 83.8 | 6.1567 | 150 | 0 | 8 |
| regex=0.72 | - | 80.0 | 83.3 | 6.2390 | 150 | 0 | 6 |
| regex=0.80 | - | 80.7 | 83.4 | 6.3528 | 150 | 0 | 5 |
| regex=0.88 | - | 83.3 | 84.5 | 6.3995 | 150 | 0 | 2 |

## e9_regex_jev_llm_l

skill: regex -> jev -> llm | tool: jev -> llm | 125000 combinações | 150 linhas (0 excluídas por erro em algum passo) | avaliador rápido == simulate_rows em 15 pontos

| método | limiares de skill | limiares de tool | conjunta dev % | US$/1k dev | conjunta CV held-out % | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.88, jev=0.76 | jev=0.50 | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) conjunta máxima sujeita ao orçamento | regex=0.88, jev=0.76 | jev=0.50 | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | 86.0 [80.0, 91.3] | 1.0621 [0.8932, 1.2605] | regex=0.89, jev=0.76 / jev=0.50 x1; regex=0.88, jev=0.79 / jev=0.50 x1; regex=0.88, jev=0.76 / jev=0.50 x3 |
| (b) regra de precisão | regex=0.88, jev=0.93 | jev=0.50 | 85.3 [79.3, 90.7] | 1.3550 [1.1422, 1.5924] | 84.0 [78.0, 89.3] | 1.2172 [1.0117, 1.4497] | regex=0.88, jev=0.93 / jev=0.50 x1; regex=0.89, jev=0.88 / jev=0.50 x1; regex=0.89, jev=0.50 / jev=0.50 x1; regex=0.67, jev=never / jev=0.50 x1; regex=0.81, jev=0.93 / jev=0.50 x1 |

Regra (b) em todas as linhas do dev:

| estágio | passo | alvo = precisão do passo seguinte | limiar | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | regex | 92.7% | 0.88 | 93.3% | 105 |
| skill | jev | 92.7% | 0.93 | 100.0% | 15 |
| tool | jev | 92.8% | 0.50 | 94.2% | 138 |

Referências no dev (todas as linhas, sem ajuste):

| referência | conjunta % [IC 95%] | US$/1k roteamento [IC 95%] |
|---|---|---|
| sempre o último (só o roteador final) | 80.0 [73.3, 86.0] | 8.8178 [8.2118, 9.4285] |
| sempre o primeiro (todo passo aceita qualquer escolha) | 80.0 [73.3, 86.0] | 0.9224 [0.7618, 1.1171] |
| oráculo (melhor passo de parada por linha) | 88.7 [83.3, 93.3] | 1.0291 [0.8557, 1.2342] |
| adiamento aleatório nas taxas de (a) conjunta máxima sujeita ao orçamento (200 sorteios, média) | 80.3 | 1.0178 |
| adiamento aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 80.2 | 1.3909 |

Fronteira de Pareto no dev (7 pontos; pareto.csv):

| limiares de skill | limiares de tool | conjunta % | cob. conjunta % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.65, jev=0.76 | jev=0.50 | 80.0 | 83.3 | 0.9206 | 150 | 0 | 6 |
| regex=0.69, jev=0.76 | jev=0.50 | 80.7 | 84.0 | 0.9212 | 150 | 0 | 6 |
| regex=0.72, jev=0.76 | jev=0.50 | 81.3 | 84.7 | 0.9387 | 150 | 0 | 6 |
| regex=0.80, jev=0.76 | jev=0.50 | 82.0 | 84.8 | 0.9743 | 150 | 0 | 5 |
| regex=0.83, jev=0.76 | jev=0.50 | 84.0 | 85.1 | 1.0077 | 150 | 0 | 2 |
| regex=0.87, jev=0.76 | jev=0.50 | 85.3 | 85.9 | 1.0120 | 150 | 0 | 1 |
| regex=0.88, jev=0.76 | jev=0.50 | 86.7 | 86.7 | 1.0337 | 150 | 0 | 0 |

## e12_hybrid_jev_llm_l

skill: hybrid -> jev -> llm | tool: jev -> llm | 125000 combinações | 150 linhas (0 excluídas por erro em algum passo) | avaliador rápido == simulate_rows em 11 pontos

| método | limiares de skill | limiares de tool | conjunta dev % | US$/1k dev | conjunta CV held-out % | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | hybrid=0.83, jev=0.77 | jev=0.50 | 82.7 [76.0, 88.0] | 1.0560 [0.8731, 1.2660] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) conjunta máxima sujeita ao orçamento | hybrid=0.78, jev=0.76 | jev=0.50 | 84.0 [78.0, 89.3] | 0.9763 [0.8130, 1.1734] | 82.7 [76.0, 88.7] | 1.0689 [0.8776, 1.2904] | hybrid=0.78, jev=0.76 / jev=0.50 x1; hybrid=0.78, jev=0.79 / jev=0.50 x1; hybrid=0.78, jev=0.76 / jev=0.55 x1; hybrid=0.93, jev=0.76 / jev=0.50 x1; hybrid=0.77, jev=0.76 / jev=0.50 x1 |
| (b) regra de precisão | hybrid=0.70, jev=never | jev=0.50 | 82.7 [76.0, 88.7] | 1.1629 [0.9705, 1.3832] | 80.7 [74.0, 86.7] | 1.1647 [0.9656, 1.3861] | hybrid=0.70, jev=never / jev=0.50 x1; hybrid=0.77, jev=0.93 / jev=0.50 x1; hybrid=0.85, jev=never / jev=0.50 x1; hybrid=0.52, jev=never / jev=0.50 x1; hybrid=0.50, jev=never / jev=0.50 x1 |

Regra (b) em todas as linhas do dev:

| estágio | passo | alvo = precisão do passo seguinte | limiar | precisão dos aceitos | n aceitos |
|---|---|---|---|---|---|
| skill | hybrid | 92.7% | 0.70 | 93.3% | 134 |
| skill | jev | 92.7% | nunca (retirar o passo) | - | 0 |
| tool | jev | 92.8% | 0.50 | 94.2% | 138 |

Referências no dev (todas as linhas, sem ajuste):

| referência | conjunta % [IC 95%] | US$/1k roteamento [IC 95%] |
|---|---|---|
| sempre o último (só o roteador final) | 80.0 [73.3, 86.0] | 8.8178 [8.2118, 9.4285] |
| sempre o primeiro (todo passo aceita qualquer escolha) | 80.0 [73.3, 86.0] | 0.9656 [0.7992, 1.1721] |
| oráculo (melhor passo de parada por linha) | 88.0 [82.7, 92.7] | 1.0046 [0.8383, 1.2062] |
| adiamento aleatório nas taxas de (a) conjunta máxima sujeita ao orçamento (200 sorteios, média) | 80.2 | 1.0337 |
| adiamento aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 80.0 | 1.2002 |

Fronteira de Pareto no dev (3 pontos; pareto.csv):

| limiares de skill | limiares de tool | conjunta % | cob. conjunta % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| hybrid=0.71, jev=0.76 | jev=0.50 | 82.7 | 86.1 | 0.9533 | 150 | 0 | 6 |
| hybrid=0.77, jev=0.76 | jev=0.50 | 83.3 | 86.8 | 0.9729 | 150 | 0 | 6 |
| hybrid=0.78, jev=0.76 | jev=0.50 | 84.0 | 87.5 | 0.9763 | 150 | 0 | 6 |
