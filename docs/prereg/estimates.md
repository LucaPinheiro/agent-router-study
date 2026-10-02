# prereg-v1 cost estimates (generated 2026-10-01T15:11:26-03:00)

`study estimate` per manifest entry (a priori, no-cache upper bound; Jev has no list price, so OpenRouter reads 0):
`uv run python scripts/analysis/prereg_estimate_apriori.py > estimate_apriori.tsv`. Expected = dev-measured $/case with cache sharing and e2e x1.3:
`uv run python scripts/analysis/prereg_estimate_expected.py estimate_apriori.tsv`. Free entries ($0 in both) are omitted.

| prio | run | mode | cases x reps | a priori bedrock | a priori openrouter | expected bedrock | expected openrouter |
|---|---|---|---|---|---|---|---|
| 20 | v2-shadow-tuned-routing-r3 | routing-only | 349x3 | 5.44 | 0.00 | 6.26 | 0.97 |
| 25 | v2-e4-jev-canonical-routing-r3 | routing-only | 349x3 | 0.00 | 0.00 | 0.00 | 0.05 |
| 25 | v2-e5-sonnet-canonical-routing-r3 | routing-only | 349x3 | 5.44 | 0.00 | 0.34 | 0.00 |
| 30 | v2-e7-tuned-routing-r3 | routing-only | 349x3 | 0.00 | 0.00 | 0.00 | 0.05 |
| 30 | v2-e9-tuned-routing-r3 | routing-only | 349x3 | 5.44 | 0.00 | 0.00 | 0.00 |
| 31 | v2-e8-tuned-routing-r3 | routing-only | 349x3 | 5.44 | 0.00 | 0.34 | 0.00 |
| 40 | v2-e6-haiku-canonical-routing-r1 | routing-only | 349x1 | 0.91 | 0.00 | 1.85 | 0.00 |
| 41 | v2-e6-haiku-canonical-rep2-60 | routing-only | 60x2 | 0.31 | 0.00 | 0.32 | 0.00 |
| 70 | lat-jev-b1 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-sonnet-b1 | routing-only | 25x1 | 0.13 | 0.00 | 0.15 | 0.00 |
| 70 | lat-haiku-b1 | routing-only | 25x1 | 0.07 | 0.00 | 0.13 | 0.00 |
| 70 | lat-e7-b1 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-e8-b1 | routing-only | 25x1 | 0.13 | 0.00 | 0.12 | 0.00 |
| 70 | lat-e9-b1 | routing-only | 25x1 | 0.13 | 0.00 | 0.07 | 0.02 |
| 70 | lat-jev-b2 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-sonnet-b2 | routing-only | 25x1 | 0.13 | 0.00 | 0.15 | 0.00 |
| 70 | lat-haiku-b2 | routing-only | 25x1 | 0.07 | 0.00 | 0.13 | 0.00 |
| 70 | lat-e7-b2 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-e8-b2 | routing-only | 25x1 | 0.13 | 0.00 | 0.12 | 0.00 |
| 70 | lat-e9-b2 | routing-only | 25x1 | 0.13 | 0.00 | 0.07 | 0.02 |
| 70 | lat-jev-b3 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-sonnet-b3 | routing-only | 25x1 | 0.13 | 0.00 | 0.15 | 0.00 |
| 70 | lat-haiku-b3 | routing-only | 25x1 | 0.07 | 0.00 | 0.13 | 0.00 |
| 70 | lat-e7-b3 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-e8-b3 | routing-only | 25x1 | 0.13 | 0.00 | 0.12 | 0.00 |
| 70 | lat-e9-b3 | routing-only | 25x1 | 0.13 | 0.00 | 0.07 | 0.02 |
| 70 | lat-jev-b4 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-sonnet-b4 | routing-only | 25x1 | 0.13 | 0.00 | 0.15 | 0.00 |
| 70 | lat-haiku-b4 | routing-only | 25x1 | 0.07 | 0.00 | 0.13 | 0.00 |
| 70 | lat-e7-b4 | routing-only | 25x1 | 0.00 | 0.00 | 0.00 | 0.02 |
| 70 | lat-e8-b4 | routing-only | 25x1 | 0.13 | 0.00 | 0.12 | 0.00 |
| 70 | lat-e9-b4 | routing-only | 25x1 | 0.13 | 0.00 | 0.07 | 0.02 |
| 80 | v2-e0-native-e2e-r1 | e2e | 349x1 | 25.30 | 0.00 | 7.43 | 0.00 |
| 80 | v2-e9-tuned-e2e-r1 | e2e | 349x1 | 27.12 | 0.00 | 4.72 | 0.03 |
| 81 | v2-e1-regex-e2e-r1 | e2e | 349x1 | 25.30 | 0.00 | 4.72 | 0.00 |
| 81 | v2-e5-sonnet-canonical-e2e-r1 | e2e | 349x1 | 27.12 | 0.00 | 4.72 | 0.00 |
| 81 | v2-e7-tuned-e2e-r1 | e2e | 349x1 | 25.30 | 0.00 | 4.72 | 0.03 |
| 82 | v2-e6b-qwen-canonical-e2e-r1 | e2e | 349x1 | 25.30 | 0.00 | 4.72 | 0.00 |
| 83 | v2-e0-native-e2e-rep2-60 | e2e | 60x1 | 4.35 | 0.00 | 1.28 | 0.00 |
| 83 | v2-e9-tuned-e2e-rep2-60 | e2e | 60x1 | 4.66 | 0.00 | 0.81 | 0.01 |
| 84 | v2-e11-hybrid-e2e-r1 | e2e | 349x1 | 25.30 | 0.00 | 4.72 | 0.00 |
| 95 | rq5-test_v2-jev-base | routing-only | 108x1 | 0.00 | 0.00 | 0.00 | 0.10 |
| 95 | rq5-test_v2-haiku-base | routing-only | 108x1 | 0.28 | 0.00 | 0.57 | 0.00 |
| 95 | rq5-test_v2-haiku-zero | routing-only | 108x1 | 0.28 | 0.00 | 0.00 | 0.00 |
| 95 | rq5-test_v2-sonnet-base | routing-only | 108x1 | 0.56 | 0.00 | 0.65 | 0.00 |
| 95 | rq5-test_v2-sonnet-zero | routing-only | 108x1 | 0.56 | 0.00 | 0.00 | 0.00 |
| 96 | x-e4-jev-p6c-routing-r1 | routing-only | 349x1 | 0.00 | 0.00 | 0.00 | 0.21 |
| 97 | x-e12-hybrid-tuned-routing-r3 | routing-only | 349x3 | 5.44 | 0.00 | 0.00 | 0.00 |
| | **total (102 entries; free entries omitted)** | | | **221.69** | **0.00** | **50.07** | **1.68** |
