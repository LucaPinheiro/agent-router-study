# Análise primária (confirmatória): prereg-v1 H1-H3 no test-v2

Gerado por `scripts/analysis/final_all.py` a partir de `results/rescored/` (scorer e0eef1fb0073). Unidade = caso (reps primeiro tiradas a média por caso); bootstrap pareado por cluster sobre os ids de caso, 10 000 reamostragens, seed 20260930; p = sign-flip no nível do caso (não inferioridade: deslocamento +0.03, unilateral); Holm step-down entre H1-H3. Intenção de tratar (ITT): uma linha com erro conta como errada.

## Contrastes: ITT (primária)

| id | run | referência | tipo | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (H1-H3) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 | E9 | E5 | non_inferiority (margem 3 pp) | 349 | -2.4 [-5.4, 0.7] | 15/21 p=0.405 | 0.3483 | 0.6965 | não | não inferioridade NÃO demonstrada |
| H2 | E7 | E5 | non_inferiority (margem 3 pp) | 349 | -4.2 [-7.8, -0.6] | 18/31 p=0.0854 | 0.7284 | 0.7284 | não | não inferioridade NÃO demonstrada |
| H3 | E9@e2e | E0@e2e | two_sided | 349 | -9.7 [-13.5, -6.0] | 6/40 p=3.1e-07 | 9.999e-05 | 0.0003 | sim | IC exclui 0 |

## Contrastes: casos sem erro em ambas as runs (sensibilidade)

| id | run | referência | tipo | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (H1-H3) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 | E9 | E5 | non_inferiority (margem 3 pp) | 349 | -2.4 [-5.4, 0.7] | 15/21 p=0.405 | 0.3483 | 0.6965 | não | não inferioridade NÃO demonstrada |
| H2 | E7 | E5 | non_inferiority (margem 3 pp) | 349 | -4.2 [-7.8, -0.6] | 18/31 p=0.0854 | 0.7284 | 0.7284 | não | não inferioridade NÃO demonstrada |
| H3 | E9@e2e | E0@e2e | two_sided | 349 | -9.7 [-13.5, -6.0] | 6/40 p=3.1e-07 | 9.999e-05 | 0.0003 | sim | IC exclui 0 |

Casos sem erro em ambas as runs: H1 349, H2 349, H3 349 (de 349).

## Estimativas co-primárias: razões de custo (bootstrap pareado por cluster da razão das médias)

| estimativa | razão | o quê | numerador US$/1k [IC 95%] | denominador US$/1k [IC 95%] | razão [IC 95%] | n casos | alvo pré-registrado |
|---|---|---|---|---|---|---|---|
| H1 co-primária | E9/E5 | US$/caso de routing, regime de cache observado (custo registrado de cada decisão) | 0.989 [0.868, 1.116] | 4.981 [4.909, 5.052] | 0.199 [0.174, 0.224] | 349 | < 0.5 (limite superior do IC < 0.5) |
| H2 (estimação) | E7/E5 | US$/caso de routing, regime de cache observado | 0.727 [0.654, 0.805] | 4.981 [4.909, 5.052] | 0.146 [0.131, 0.162] | 349 |  |
| H3 co-primária | E9/E0 | US$/turno, routing + executor, observado | 8.206 [7.722, 8.734] | 9.031 [8.533, 9.576] | 0.909 [0.859, 0.960] | 349 |  |

## Resultado principal por run (ITT, IC 95% por bootstrap de cluster)

| run | métrica | linhas | linhas com erro | % [IC 95%] |
|---|---|---|---|---|
| v2-e5-sonnet-canonical-routing-r3 | joint | 1047 | 0 | 84.1 [80.3, 87.8] |
| v2-e7-tuned-routing-r3 | joint | 1047 | 0 | 79.9 [75.8, 84.0] |
| v2-e9-tuned-routing-r3 | joint | 1047 | 0 | 81.8 [77.8, 85.6] |
| v2-e0-native-e2e-r1 | e2e_success | 349 | 0 | 55.6 [50.1, 60.7] |
| v2-e9-tuned-e2e-r1 | e2e_success | 349 | 0 | 45.8 [40.4, 51.0] |

## Leitura

- Regra de decisão de H1/H2 (pré-registrada): não inferior sse o limite inferior do IC pareado bilateral de 95% de Δ (= unilateral de 97.5%) estiver acima de -3 pp. O p sign-flip ajustado por Holm testa H0: Δ <= -3 pp. O veredito do IC e a decisão de Holm são ambos reportados; quando divergem, a regra do IC é a decisão pré-registrada e a coluna Holm é o teste com controle de multiplicidade.
- H3: bilateral; uma afirmação direcional só se o IC excluir 0.
- E5 é a run canônica do Sonnet; tuned == canonical (P0) para todo router LLM, então ela também é a referência tuned.
- E9/E7/E5 só de routing reutilizam as mesmas amostras de Sonnet/Jev do shadow pass (cache de respostas por caso, rep, prompt): o pareamento é por construção, e o custo registrado delas é o custo original (independente de cache) de cada decisão.
