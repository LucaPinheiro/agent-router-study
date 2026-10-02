# Análises end-to-end exploratórias (test-v2; post hoc, NÃO confirmatórias)

Gerado por `scripts/analysis/final_all.py` (módulo `final_exploratory.py`) a partir de `results/rescored/`. ITT; bootstrap pareado por cluster sobre os ids de caso, 10k reamostragens, seed 20260930. Todo resultado aqui foi desenhado depois que os resultados pré-registrados foram vistos (desvio D-002) e usa o mesmo split de teste: serve apenas para gerar hipóteses.

## 1. Desvio D-002: rotear a skill, expor todas as suas tools (EXPLORATÓRIO, post hoc)

`x-e9-fullskill-e2e-r1` / `x-e7-fullskill-e2e-r1` = as configs congeladas de E9 / E7 com `routing.tool.expose_top_k: 5` (todas as 5 tools da skill roteada + as 3 tools globais expostas ao executor Sonnet 5) em vez do top-2 pré-registrado. As decisões do router são cache hits de resposta das mesmas amostras (pareadas por construção); só o executor é reamostrado. Desenhado DEPOIS de ver H3 no mesmo split: gera hipóteses, não é confirmatório; p-valores não ajustados e descritivos.

### Scores e2e (ITT, 1 rep, 349 casos; % [IC 95% por cluster bootstrap])

| run | linhas | erros | e2e_success | = primeira chamada | + clarificação | + recuperado | skill | tool na primeira chamada | args válidos | tools expostas/turno (média) | turnos em loop_limit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E0 nativo (sem router) | 349 | 0 | 55.6 [50.1, 60.7] | 53.3 [47.9, 58.5] | 1.4 [0.3, 2.9] | 0.9 [0.0, 2.0] | 88.8 [85.4, 92.0] | 75.1 [70.5, 79.7] | 68.5 [63.3, 73.4] | 6.80 | 23 |
| E9 regex->Jev->Sonnet | 349 | 0 | 45.8 [40.4, 51.0] | 45.0 [39.8, 50.1] | 0.9 [0.0, 2.0] | 0.0 [0.0, 0.0] | 85.4 [81.7, 89.1] | 73.9 [69.3, 78.5] | 66.2 [61.0, 71.1] | 4.61 | 1 |
| E7 regex->Jev | 349 | 0 | 45.0 [39.8, 50.1] | 43.6 [38.4, 48.7] | 1.1 [0.3, 2.3] | 0.3 [0.0, 0.9] | 83.7 [79.7, 87.4] | 73.9 [69.1, 78.5] | 67.0 [61.9, 71.9] | 4.62 | 1 |
| E9 regex->Jev->Sonnet, todas as tools da skill expostas (D-002) | 349 | 0 | 48.1 [43.0, 53.3] | 47.6 [42.4, 52.7] | 0.6 [0.0, 1.4] | 0.0 [0.0, 0.0] | 85.1 [81.4, 88.8] | 75.1 [70.5, 79.4] | 67.6 [62.8, 72.5] | 7.03 | 2 |
| E7 regex->Jev, todas as tools da skill expostas (D-002) | 349 | 0 | 44.7 [39.5, 49.9] | 43.6 [38.4, 48.7] | 0.9 [0.0, 2.0] | 0.3 [0.0, 0.9] | 84.0 [79.9, 87.7] | 71.3 [66.5, 75.9] | 65.6 [60.5, 70.5] | 7.05 | 2 |

Skill roteada idêntica à da run top-2 em E9-full 349/349, E7-full 349/349 casos (mesmas amostras do router em cache).

### Contrastes pareados (EXPLORATÓRIO; não ajustados)

E9 - E0 é o contraste pré-registrado de H3 (primary.md), repetido aqui como referência.

| contraste | score | n casos | Δ pp [IC 95%] (bootstrap pareado por cluster) | McNemar só-run/só-ref | p exato McNemar | p sign-flip |
|---|---|---|---|---|---|---|
| E9-full - E9 | e2e_success | 349 | 2.3 [0.0, 4.6] | 12/4 | 0.0768 | 0.0768 |
| E9-full - E9 | first_call_success | 349 | 2.6 [0.6, 4.9] | 12/3 | 0.0352 | 0.0352 |
| E9-full - E9 | tool_correct | 349 | 1.1 [-1.4, 3.7] | 12/8 | 0.503 | 0.503 |
| E9-full - E0 | e2e_success | 349 | -7.4 [-11.5, -3.4] | 13/39 | 0.00041 | 0.0003 |
| E9-full - E0 | first_call_success | 349 | -5.7 [-9.7, -1.7] | 15/35 | 0.0066 | 0.0066 |
| E9-full - E0 | tool_correct | 349 | 0.0 [-3.4, 3.4] | 18/18 | 1 | 1 |
| E7-full - E7 | e2e_success | 349 | -0.3 [-2.3, 2.0] | 7/8 | 1 | 1 |
| E7-full - E7 | first_call_success | 349 | 0.0 [-2.0, 2.0] | 7/7 | 1 | 1 |
| E7-full - E7 | tool_correct | 349 | -2.6 [-5.2, 0.0] | 7/16 | 0.0931 | 0.09 |
| E7-full - E0 | e2e_success | 349 | -10.9 [-14.9, -6.9] | 8/46 | 1.38e-07 | 0.0001 |
| E7-full - E0 | first_call_success | 349 | -9.7 [-13.8, -5.7] | 10/44 | 3.39e-06 | 0.0001 |
| E7-full - E0 | tool_correct | 349 | -3.7 [-7.2, -0.3] | 11/24 | 0.041 | 0.0363 |
| E9 - E0 | e2e_success | 349 | -9.7 [-13.5, -6.0] | 6/40 | 3.1e-07 | 0.0001 |
| E9 - E0 | first_call_success | 349 | -8.3 [-12.0, -4.6] | 8/37 | 1.54e-05 | 0.0001 |
| E9 - E0 | tool_correct | 349 | -1.1 [-4.6, 2.3] | 16/20 | 0.618 | 0.62 |
| E7 - E0 | e2e_success | 349 | -10.6 [-14.6, -6.9] | 8/45 | 2.37e-07 | 0.0001 |
| E7 - E0 | first_call_success | 349 | -9.7 [-13.8, -5.7] | 10/44 | 3.39e-06 | 0.0001 |
| E7 - E0 | tool_correct | 349 | -1.1 [-5.2, 2.6] | 21/25 | 0.659 | 0.655 |

### Custo por turno e tokens (regime observado)

| run | US$/1k turnos total [IC] | routing [IC] | executor [IC] | tokens de prompt do executor/turno [IC] | tokens de completion/turno [IC] | chamadas do executor/turno |
|---|---|---|---|---|---|---|
| E0 nativo (sem router) | 9.03 [8.53, 9.58] | 0.00 [0.00, 0.00] | 9.03 [8.53, 9.58] | 14737 [13994, 15516] | 367 [347, 388] | 2.79 |
| E9 regex->Jev->Sonnet | 8.21 [7.72, 8.73] | 1.01 [0.88, 1.14] | 7.20 [6.74, 7.69] | 8734 [8340, 9142] | 333 [311, 357] | 1.97 |
| E7 regex->Jev | 7.87 [7.40, 8.37] | 0.76 [0.68, 0.84] | 7.11 [6.66, 7.59] | 8858 [8461, 9278] | 347 [323, 373] | 1.99 |
| E9 regex->Jev->Sonnet, todas as tools da skill expostas (D-002) | 8.33 [7.86, 8.85] | 1.01 [0.88, 1.14] | 7.32 [6.88, 7.80] | 11092 [10582, 11631] | 339 [317, 364] | 2.00 |
| E7 regex->Jev, todas as tools da skill expostas (D-002) | 7.97 [7.50, 8.46] | 0.76 [0.68, 0.84] | 7.21 [6.77, 7.68] | 11062 [10532, 11610] | 342 [317, 368] | 1.98 |

Razões pareadas das médias (cluster bootstrap):

| razão | grandeza | n casos | razão [IC 95%] |
|---|---|---|---|
| E9-full / E0 | US$/turno | 349 | 0.922 [0.879, 0.969] |
| E9-full / E0 | tokens de prompt/turno | 349 | 0.753 [0.728, 0.778] |
| E9-full / E9 | US$/turno | 349 | 1.015 [0.970, 1.063] |
| E9-full / E9 | tokens de prompt/turno | 349 | 1.270 [1.236, 1.307] |
| E7-full / E0 | US$/turno | 349 | 0.882 [0.838, 0.929] |
| E7-full / E0 | tokens de prompt/turno | 349 | 0.751 [0.724, 0.778] |
| E7-full / E7 | US$/turno | 349 | 1.013 [0.963, 1.066] |
| E7-full / E7 | tokens de prompt/turno | 349 | 1.249 [1.211, 1.287] |

## 2. Por que o e2e roteado fica abaixo do E0 nativo? Análise de erros nos casos discordantes (EXPLORATÓRIO)

Unidade: caso (1 rep cada). Um caso discordante tem sucesso (e2e_success) em exatamente uma das duas runs. Cada um recebe UMA classe, pela primeira regra que casar, na ordem listada. `business calls` = as chamadas de tools MCP que o servidor executou (sem `load_skill`). `native >1 load_skill` conta os casos discordantes em que o E0 carregou duas skills (trocou de skill) naquele turno. As classes são mecânicas (a partir das linhas registradas), não um julgamento humano das transcrições.

Nota de pontuação (classe A): numa run roteada, a skill do e2e é o rótulo de skill do ROUTER; no E0 é a primeira skill que o agente carrega (`__abstain__` quando não fez nenhuma chamada, `__global__` quando só usou tools globais; docs/metrics.md). Assim, um turno roteado cujo executor fez exatamente o que o agente nativo fez (ex.: recusou um pedido fora de escopo sem nenhuma chamada, ou chamou a global `search_help_center`) ainda falha quando o router rotulou uma skill errada (ex.: `__global__` em vez de `__abstain__`). Este é o scorer pré-registrado e NÃO é alterado aqui; a classe A só mede quanto do gap ele explica.

### E9 (tools top-2, pré-registrado) vs E0

Casos 349; sucessos só do nativo **40**, sucessos só do roteado **6** (líquido -34 casos = -9.7 pp). Só do nativo por categoria: fora_escopo 16, parafrase 12, ambiguo 7, adversarial 2, multiturno 2, direto 1.

Nativo teve sucesso, E9 falhou (40 casos):

| classe | por que o turno roteado falhou | casos | fração | tem sucesso em E9-full (D-002) | exemplos |
|---|---|---|---|---|---|
| A1 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold fora de escopo | 17 | 42% | 0/17 | v2-adversarial-007, v2-fora_escopo-008, v2-fora_escopo-011, v2-fora_escopo-012 |
| A2 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold dentro do escopo | 5 | 12% | 0/5 | v2-direto-011, v2-multiturno-003, v2-parafrase-006, v2-parafrase-009 |
| B | skill roteada errada e o executor agiu de forma diferente (o erro de routing mudou o turno) | 7 | 18% | 0/7 | v2-ambiguo-002, v2-ambiguo-035, v2-parafrase-051, v2-parafrase-052 |
| C | skill roteada certa, mas nenhuma tool aceitável exposta ao executor | 1 | 2% | 1/1 | v2-parafrase-020 |
| D | nativo creditado por uma pergunta de clarificação; o executor roteado não a fez | 2 | 5% | 0/2 | v2-ambiguo-013, v2-parafrase-031 |
| E | nativo se recuperou com uma chamada posterior; o roteado não | 1 | 2% | 0/1 | v2-ambiguo-016 |
| F | tool aceitável exposta; a primeira business call do executor roteado difere da do nativo | 6 | 15% | 3/6 | v2-ambiguo-023, v2-ambiguo-055, v2-ambiguo-066, v2-multiturno-027 |
| G | mesma primeira business call do nativo, mas args do roteado inválidos / chamada não concluída | 1 | 2% | 1/1 | v2-adversarial-001 |

Sensibilidade post hoc (NÃO é o scorer pré-registrado): se os 22 turnos da classe A fossem pontuados pelo comportamento, como no nativo, o e2e_success de E9 seria 52.1% e E9 - E0 = -3.4 [-6.3, -0.9] pp.

E9 teve sucesso, nativo falhou (6 casos):

| classe | por que o nativo falhou | casos | fração |
|---|---|---|---|
| N1 | o nativo respondeu sem nenhuma business call; o executor roteado agiu (e teve sucesso) | 3 | 50% |
| N3 | o nativo atingiu o limite de loop | 1 | 17% |
| N4 | mesma primeira business call, args do nativo inválidos / chamada não concluída | 2 | 33% |

O nativo carregou duas skills (`load_skill` duas vezes) em 1 dos casos só do nativo e em 1 dos casos só do roteado.

### E9 com todas as tools da skill expostas (D-002) vs E0

Casos 349; sucessos só do nativo **39**, sucessos só do roteado **13** (líquido -26 casos = -7.4 pp). Só do nativo por categoria: fora_escopo 17, parafrase 10, ambiguo 8, multiturno 2, adversarial 1, direto 1.

Nativo teve sucesso, E9-full falhou (39 casos):

| classe | por que o turno roteado falhou | casos | fração | exemplos |
|---|---|---|---|---|
| A1 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold fora de escopo | 18 | 46% | v2-adversarial-007, v2-fora_escopo-008, v2-fora_escopo-010, v2-fora_escopo-011 |
| A2 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold dentro do escopo | 5 | 13% | v2-direto-011, v2-multiturno-003, v2-parafrase-006, v2-parafrase-009 |
| B | skill roteada errada e o executor agiu de forma diferente (o erro de routing mudou o turno) | 7 | 18% | v2-ambiguo-002, v2-ambiguo-035, v2-parafrase-051, v2-parafrase-052 |
| D | nativo creditado por uma pergunta de clarificação; o executor roteado não a fez | 3 | 8% | v2-ambiguo-013, v2-parafrase-031, v2-parafrase-075 |
| E | nativo se recuperou com uma chamada posterior; o roteado não | 1 | 3% | v2-ambiguo-016 |
| F | tool aceitável exposta; a primeira business call do executor roteado difere da do nativo | 5 | 13% | v2-ambiguo-023, v2-ambiguo-026, v2-ambiguo-042, v2-ambiguo-055 |

Sensibilidade post hoc (NÃO é o scorer pré-registrado): se os 23 turnos da classe A fossem pontuados pelo comportamento, como no nativo, o e2e_success de E9-full seria 54.7% e E9-full - E0 = -0.9 [-4.0, 2.3] pp.

E9-full teve sucesso, nativo falhou (13 casos):

| classe | por que o nativo falhou | casos | fração |
|---|---|---|---|
| N1 | o nativo respondeu sem nenhuma business call; o executor roteado agiu (e teve sucesso) | 4 | 31% |
| N3 | o nativo atingiu o limite de loop | 1 | 8% |
| N4 | mesma primeira business call, args do nativo inválidos / chamada não concluída | 6 | 46% |
| N5 | a primeira business call do nativo difere da do roteado (outros) | 2 | 15% |

O nativo carregou duas skills (`load_skill` duas vezes) em 1 dos casos só do nativo e em 1 dos casos só do roteado.

### E7 (top-2) vs E0

Casos 349; sucessos só do nativo **45**, sucessos só do roteado **8** (líquido -37 casos = -10.6 pp). Só do nativo por categoria: fora_escopo 20, parafrase 11, ambiguo 9, adversarial 2, multiturno 2, direto 1.

Nativo teve sucesso, E7 falhou (45 casos):

| classe | por que o turno roteado falhou | casos | fração | exemplos |
|---|---|---|---|---|
| A1 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold fora de escopo | 21 | 47% | v2-adversarial-007, v2-adversarial-008, v2-fora_escopo-004, v2-fora_escopo-008 |
| A2 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold dentro do escopo | 5 | 11% | v2-direto-011, v2-multiturno-001, v2-parafrase-006, v2-parafrase-009 |
| B | skill roteada errada e o executor agiu de forma diferente (o erro de routing mudou o turno) | 8 | 18% | v2-ambiguo-002, v2-ambiguo-044, v2-fora_escopo-027, v2-parafrase-051 |
| C | skill roteada certa, mas nenhuma tool aceitável exposta ao executor | 2 | 4% | v2-ambiguo-051, v2-parafrase-020 |
| D | nativo creditado por uma pergunta de clarificação; o executor roteado não a fez | 1 | 2% | v2-parafrase-031 |
| F | tool aceitável exposta; a primeira business call do executor roteado difere da do nativo | 8 | 18% | v2-ambiguo-010, v2-ambiguo-017, v2-ambiguo-023, v2-ambiguo-024 |

Sensibilidade post hoc (NÃO é o scorer pré-registrado): se os 26 turnos da classe A fossem pontuados pelo comportamento, como no nativo, o e2e_success de E7 seria 52.4% e E7 - E0 = -3.2 [-6.0, -0.3] pp.

E7 teve sucesso, nativo falhou (8 casos):

| classe | por que o nativo falhou | casos | fração |
|---|---|---|---|
| N1 | o nativo respondeu sem nenhuma business call; o executor roteado agiu (e teve sucesso) | 2 | 25% |
| N3 | o nativo atingiu o limite de loop | 1 | 12% |
| N4 | mesma primeira business call, args do nativo inválidos / chamada não concluída | 4 | 50% |
| N5 | a primeira business call do nativo difere da do roteado (outros) | 1 | 12% |

O nativo carregou duas skills (`load_skill` duas vezes) em 2 dos casos só do nativo e em 1 dos casos só do roteado.

### E7 com todas as tools da skill expostas (D-002) vs E0

Casos 349; sucessos só do nativo **46**, sucessos só do roteado **8** (líquido -38 casos = -10.9 pp). Só do nativo por categoria: fora_escopo 19, ambiguo 11, parafrase 10, multiturno 3, adversarial 2, direto 1.

Nativo teve sucesso, E7-full falhou (46 casos):

| classe | por que o turno roteado falhou | casos | fração | exemplos |
|---|---|---|---|---|
| A1 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold fora de escopo | 18 | 39% | v2-adversarial-007, v2-adversarial-008, v2-fora_escopo-008, v2-fora_escopo-009 |
| A2 | rótulo de skill roteado não aceito, comportamento do executor idêntico ao nativo (mesmas business calls) - gold dentro do escopo | 5 | 11% | v2-direto-011, v2-multiturno-001, v2-parafrase-006, v2-parafrase-009 |
| B | skill roteada errada e o executor agiu de forma diferente (o erro de routing mudou o turno) | 10 | 22% | v2-ambiguo-002, v2-ambiguo-044, v2-fora_escopo-004, v2-fora_escopo-023 |
| D | nativo creditado por uma pergunta de clarificação; o executor roteado não a fez | 2 | 4% | v2-ambiguo-013, v2-parafrase-031 |
| F | tool aceitável exposta; a primeira business call do executor roteado difere da do nativo | 11 | 24% | v2-ambiguo-010, v2-ambiguo-017, v2-ambiguo-023, v2-ambiguo-024 |

Sensibilidade post hoc (NÃO é o scorer pré-registrado): se os 23 turnos da classe A fossem pontuados pelo comportamento, como no nativo, o e2e_success de E7-full seria 51.3% e E7-full - E0 = -4.3 [-7.4, -1.1] pp.

E7-full teve sucesso, nativo falhou (8 casos):

| classe | por que o nativo falhou | casos | fração |
|---|---|---|---|
| N1 | o nativo respondeu sem nenhuma business call; o executor roteado agiu (e teve sucesso) | 1 | 12% |
| N3 | o nativo atingiu o limite de loop | 1 | 12% |
| N4 | mesma primeira business call, args do nativo inválidos / chamada não concluída | 6 | 75% |

O nativo carregou duas skills (`load_skill` duas vezes) em 2 dos casos só do nativo e em 1 dos casos só do roteado.

### Carregamento de skills no E0 nativo (todos os 349 casos)

`load_skill` chamado uma vez em 244 turnos, duas vezes em 21 (e2e_success 10/21), nunca em 84 (tools globais ou nenhuma chamada; e2e_success 58/84).

## 3. Pares confundíveis em só routing (descritivo)

Rep 1 de cada run (349 casos), apenas linhas com joint errado: gold = primeira tool aceitável listada (`__abstain__` para fora de escopo), previsto = a tool top-1 do router (`__abstain__` quando ele se absteve; linhas com skill errada incluídas). Casos multi-rótulo só contam quando nenhum rótulo aceitável foi previsto. `[skill X]` = a tool era aceitável, mas a skill roteada X não era (um erro no estágio de skill). Top 6 pares por router.

| router | casos com joint errado (rep 1) | principais confusões: gold -> previsto (n) |
|---|---|---|
| E1 regex | 165 | get_order_status -> __abstain__ (11); cancel_order -> __abstain__ (8); escalate_to_human -> __abstain__ (7); create_return_request -> __abstain__ (6); search_help_center -> __abstain__ (5); reschedule_delivery -> __abstain__ (5) |
| E3 embedding (qwen3-emb 8B) | 92 | get_order_status -> track_shipment (8); cancel_order -> check_return_eligibility (5); request_refund -> create_return_request (5); search_help_center -> create_return_request (4); search_help_center -> cancel_order (3); __abstain__ -> search_help_center (3) |
| E10 classificador (probe) | 88 | get_order_status -> track_shipment (6); search_help_center -> create_return_request (5); request_refund -> create_return_request (4); get_order_status -> get_customer_profile (3); __abstain__ -> search_help_center (3); create_return_request -> escalate_to_human (3) |
| E6b Qwen3-8B local | 70 | escalate_to_human -> escalate_to_human [skill pedidos_logistica] (5); request_refund -> create_return_request (4); get_order_status -> track_shipment (3); search_help_center -> search_help_center [skill trocas_devolucoes] (3); track_shipment -> get_order_status (3); get_payment_status -> request_refund (3) |
| E4 Jev | 56 | request_refund -> create_return_request (5); track_shipment -> get_order_status (4); create_return_request -> check_return_eligibility (4); search_help_center -> search_help_center [skill trocas_devolucoes] (3); get_order_status -> track_shipment (3); __abstain__ -> search_help_center (2) |
| E5 Sonnet 5 | 53 | get_order_status -> track_shipment (5); request_refund -> create_return_request (4); open_warranty_claim -> create_return_request (3); search_help_center -> search_help_center [skill trocas_devolucoes] (2); __abstain__ -> get_customer_profile (2); __abstain__ -> search_help_center (2) |
| E9 regex->Jev->Sonnet | 65 | search_help_center -> search_help_center [skill trocas_devolucoes] (4); track_shipment -> get_order_status (4); create_return_request -> check_return_eligibility (3); get_order_status -> track_shipment (3); request_refund -> create_return_request (3); open_warranty_claim -> create_return_request (2) |
