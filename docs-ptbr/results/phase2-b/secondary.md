# Análises secundárias da Parte B [C]: famílias S-e2e e S-routing no `test_l`

> Tradução pt-BR de [`docs/results/phase2-b/secondary.md`](../../../docs/results/phase2-b/secondary.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

Mesma maquinaria de primary.md; Holm dentro de cada família (uma hipótese não rodada entra com p = 1; S5 e S6 foram retiradas: o braço de referência delas é local e nenhum modelo local roda na fase 2).

## Família S-e2e (Holm dentro) [C]

- **S1:** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, unilateral (confirma o D-002 num split novo).
- **S2:** e2e_success_sym(E9-L) − e2e_success_sym(E0-L) nos casos em que os dois braços executaram a mesma sequência de chamadas de negócio; equivalência ±3 pp (TOST, IC 90% dentro). Casos com as mesmas chamadas: **225**.

| id | run | referência | tipo | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (família) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | E9-full@e2e | E9@e2e | greater (margem 3 pp) | 300 | -0.3 [-2.7, 1.7] | 5/6 p=1 | 0.7256 | 0.7256 | não | IC inclui 0 (sem afirmação direcional) |
| S2 | E9@e2e | E0@e2e | equivalence (margem 3 pp) | 225 | 1.8 [0.4, 3.6] | 4/0 p=0.125 | 0.07589 | 0.1518 | não | inconclusivo |

## Família S-routing (Holm dentro) [C]

### S3: regex conjunta test-L − CV dev-L < 0 (magnitude com IC; dev fixo; regra do IC, sem p-valor)

| roteador | conjunta dev-L % | conjunta teste % [IC 95%] | gap pp [IC 95%] | veredito |
|---|---|---|---|---|
| E1 regex | 82.7 | 56.3 [50.7, 62.0] | -26.4 [-32.0, -20.7] | gap < 0 (IC do teste inteiro abaixo do dev) |

### S4-S7

- **S4:** Conjunta(E3 embedding, Bedrock Titan v2) − Conjunta(E1 regex), bilateral.
- **S5 (retirada):** Conjunta(E3c Cohere) − Conjunta(E3 LOCAL): sem braço local no test-L.
- **S6 (retirada):** Conjunta(E6n Nemotron) − Conjunta(E6b Qwen3-8B LOCAL) > −3 pp: sem braço local no test-L.
- **S7:** Conjunta(E10, melhor sonda pré-declarada) − Conjunta(E4 Jev), bilateral.

| id | run | referência | tipo | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar nível de caso só-run/só-ref | p sign-flip | p Holm (família) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| S4 | E3 | E1 | two_sided | 300 | 3.7 [-3.3, 10.3] | 58/47 p=0.329 | 0.343 | 0.343 | não | IC inclui 0 (sem afirmação direcional) |
| S5 | E3c | E3-local | two_sided | - | falta E3c: run ausente ou não COMPLETE |  |  | - | - | **RETIRADA** (atualização de restrição; fora da família de Holm) |
| S6 | E6n | E6b | non_inferiority | - | falta E6b: nenhum modelo local na fase 2 (restrição 2026-10-02): sem braço Qwen3-8B no test-L |  |  | - | - | **RETIRADA** (atualização de restrição; fora da família de Holm) |
| S7 | E10 | E4 | two_sided | 300 | -25.9 [-31.7, -20.0] | 11/94 p=1.39e-17 | 9.999e-05 | 0.0002 | sim | IC exclui 0 (run menor) |
