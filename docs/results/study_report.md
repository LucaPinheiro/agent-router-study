# shadow run shadow-dev-routing-only.jsonl: 151 cases

## strategies (isolated)

| strategy | n | skill % | tool % (cond.) | joint % | n_cmp | ECE | p50 ms | p95 ms | US$/1k |
|---|---|---|---|---|---|---|---|---|---|
| regex | 151 | 62.3 | 62.0 | 42.1 | 76 | 0.218 | 0 | 0 | 0.0000 |
| bm25 | 151 | 55.6 | 69.8 | 39.0 | 67 | 0.230 | 0 | 0 | 0.0000 |
| embedding | 151 | 70.2 | 86.1 | 59.6 | 120 | 0.089 | 5846 | 33863 | 0.0005 |
| hybrid | 151 | 58.9 | 81.0 | 45.4 | 94 | 0.136 | 5017 | 25083 | 0.0004 |
| jev | 151 | 84.1 | 83.2 | 69.8 | 148 | 0.131 | 5481 | 10641 | 0.4326 |
| llm | 151 | 83.4 | 81.3 | 67.8 | 145 | 0.068 | 13827 | 38266 | 2.3107 |
| e6-haiku-dev-routing-only (real run) | 151 | 83.4 | 84.9 | 70.9 | 151 | - | 3435 | 56077 | 3.4010 |

## skill accuracy by category

| strategy | direto | parafrase | ambiguo | multiturno | fora_escopo | adversarial |
|---|---|---|---|---|---|---|
| regex | 82.2 | 42.1 | 56.7 | 20.0 | 100.0 | 75.0 |
| bm25 | 71.1 | 39.5 | 60.0 | 20.0 | 80.0 | 50.0 |
| embedding | 80.0 | 84.2 | 76.7 | 26.7 | 26.7 | 87.5 |
| hybrid | 73.3 | 55.3 | 73.3 | 20.0 | 20.0 | 87.5 |
| jev | 93.3 | 86.8 | 90.0 | 86.7 | 26.7 | 100.0 |
| llm | 95.6 | 84.2 | 83.3 | 86.7 | 33.3 | 100.0 |
| e6-haiku-dev-routing-only | 93.3 | 84.2 | 90.0 | 86.7 | 26.7 | 100.0 |

## simulated cascades (offline replay of the shadow decisions)

| config | skill % | tool % | US$/1k routing | ms/case routing | resolved_by |
|---|---|---|---|---|---|
| e1_regex | 62.3 | 46.9 (n=130) | 0.0000 | 0 | {'regex': 97, 'abstained': 54} |
| e2_bm25 | 55.6 | 53.4 (n=103) | 0.0000 | 0 | {'bm25': 115, 'abstained': 36} |
| e3_embedding | 70.2 | 72.5 (n=120) | 0.0005 | 9912 | {'embedding': 151} |
| e4_jev | 84.1 | 71.6 (n=148) | 0.4326 | 5905 | {'jev': 151} |
| e5_llm_sonnet | 83.4 | 70.5 (n=149) | 2.3107 | 17467 | {'llm': 147, 'abstained': 4} |
| e7_regex_jev | 84.1 | 71.5 (n=151) | 0.4247 | 5380 | {'regex': 33, 'jev': 118} |
| e8_regex_llm | 84.1 | 70.7 (n=150) | 2.1664 | 16004 | {'regex': 33, 'llm': 115, 'abstained': 3} |
| e9_regex_jev_llm | 84.1 | 70.2 (n=151) | 0.6196 | 6323 | {'regex': 33, 'llm': 4, 'jev': 114} |

## top errors per strategy

- **regex**: skill pedidos_logistica -> __abstain__ (15); skill trocas_devolucoes -> pedidos_logistica (10); skill pagamentos_reembolsos -> __abstain__ (7); skill trocas_devolucoes -> __abstain__ (7); tool request_refund/cancel_order/track_shipment -> __abstain__ (4)
- **bm25**: skill trocas_devolucoes -> pedidos_logistica (10); skill pedidos_logistica -> __abstain__ (8); skill pagamentos_reembolsos -> __global__ (8); skill trocas_devolucoes -> __global__ (6); skill trocas_devolucoes -> __abstain__ (6)
- **embedding**: skill trocas_devolucoes -> __global__ (7); skill pagamentos_reembolsos -> trocas_devolucoes (7); skill __abstain__ -> __global__ (6); skill pedidos_logistica -> __global__ (6); skill pagamentos_reembolsos -> __global__ (4)
- **hybrid**: skill pagamentos_reembolsos -> __global__ (11); skill trocas_devolucoes -> pedidos_logistica (11); skill trocas_devolucoes -> __global__ (7); skill __abstain__ -> __global__ (7); skill pedidos_logistica -> __global__ (7)
- **jev**: skill __abstain__ -> __global__ (10); skill pagamentos_reembolsos -> trocas_devolucoes (7); skill __global__ -> pedidos_logistica (2); tool get_order_status -> track_shipment (2); tool track_shipment -> get_order_status (2)
- **llm**: skill __abstain__ -> __global__ (9); skill pagamentos_reembolsos -> trocas_devolucoes (5); skill pedidos_logistica/trocas_devolucoes -> __abstain__ (2); tool get_order_status/escalate_to_human -> __abstain__ (2); skill __global__ -> pedidos_logistica (2)
