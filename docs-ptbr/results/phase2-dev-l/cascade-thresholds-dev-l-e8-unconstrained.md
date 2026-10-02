# Calibração de limiares de cascata: freeze-dev-l-shadow-r1.jsonl

> Tradução pt-BR de [`docs/results/phase2-dev-l/cascade-thresholds-dev-l-e8-unconstrained.md`](../../../docs/results/phase2-dev-l/cascade-thresholds-dev-l-e8-unconstrained.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

- origem: freeze-dev-l-shadow-r1.jsonl (150 linhas), dataset dataset_dev_l.jsonl b02b3722f5c4, scorer e0eef1fb0073, run git ['5d7ffc6']
- grade 0.50..0.99 (50 valores) por passo que não é o último; sem orçamento (máxima acurácia conjunta); CV de 5 folds estratificada por categoria sobre os ids de caso, seed 0; regra (b) com suporte mínimo de 5 casos aceitos
- intenção de tratar: toda linha conta; um estágio de roteamento que falhou (erro ou falha de parse) é ERRADO, nunca uma abstenção, então um limiar não pode ganhar mandando casos que falham para um erro; conjunta %: um estágio de tool que não pode ser reproduzido (skill simulada diferente da gravada) conta 0 (limite inferior); custo de roteamento US$/1k sobre as linhas cobertas; ICs 95%: bootstrap por cluster sobre os ids de caso (`eval/stats.py`, seed fixa)
- 'dev' = ajustado e pontuado em todas as linhas do dev (otimista); 'CV held-out' = reajustado em k-1 folds, pontuado no fold separado, reunido
- confianças como gravadas: 582/582 decisões de regex/BM25 carregam `usage.raw_confidence` (0 = a run é anterior aos mapas de calibração: os seus limiares estão na escala bruta; rode de novo a run shadow com a config atual antes de aplicá-los)

## e8_regex_llm_l

skill: regex -> llm | tool: llm | 50 combinações | 150 linhas (0 excluídas por erro em algum passo) | avaliador rápido == simulate_rows em 12 pontos

| método | limiares de skill | limiares de tool | conjunta dev % | US$/1k dev | conjunta CV held-out % | US$/1k CV | escolhas por fold |
|---|---|---|---|---|---|---|---|
| configurado (YAML) | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | = dev (sem ajuste) | = dev | (sem ajuste) |
| (a) conjunta máxima sujeita ao orçamento | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | regex=0.88 / - x5 |
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
| adiamento aleatório nas taxas de (a) conjunta máxima sujeita ao orçamento (200 sorteios, média) | 79.5 | 6.5146 |
| adiamento aleatório nas taxas de (b) regra de precisão (200 sorteios, média) | 79.5 | 6.5146 |

Fronteira de Pareto no dev (4 pontos; pareto.csv):

| limiares de skill | limiares de tool | conjunta % | cob. conjunta % | US$/1k | n | err | indisp. |
|---|---|---|---|---|---|---|---|
| regex=0.58 | - | 79.3 | 83.8 | 6.1567 | 150 | 0 | 8 |
| regex=0.72 | - | 80.0 | 83.3 | 6.2390 | 150 | 0 | 6 |
| regex=0.80 | - | 80.7 | 83.4 | 6.3528 | 150 | 0 | 5 |
| regex=0.88 | - | 83.3 | 84.5 | 6.3995 | 150 | 0 | 2 |
