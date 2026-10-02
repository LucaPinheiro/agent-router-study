# Enterprise decision matrix (test-v2, routing-only)

For each latency SLO (warm p95, dedicated lat-* benchmark), routing-cost ceiling (US$ per 1 000 cases, observed regime) and minimum joint accuracy (ITT), the qualifying configuration with the highest joint accuracy (ties: lower cost). Qualification uses point estimates; `robust` = the 95% CIs also satisfy all three constraints (joint CI lower bound >= floor, p95 CI upper bound < SLO, cost CI upper bound <= ceiling). Estimation only (no test); the paired differences between the top candidates are in primary.md / secondary.md and mostly within a few pp with overlapping CIs, so a cell's winner is not 'significantly best'.

Caveats: routing-only joint (not e2e success: see estimation.md J, where every routed config is below the native E0 executor); latency measured on one machine / one network at concurrency 1 (API latency includes provider queueing); local model cost is counted as US$ 0 (hardware and energy excluded); Jev's cost is its reported OpenRouter price (no list price).

## Candidates

| config | where | joint % [95% CI] | warm p95 ms [95% CI] | US$/1k observed [95% CI] | US$/1k list uncached |
|---|---|---|---|---|---|
| E4 Jev | API | 84.7 [81.0, 88.2] | 6851.1 [6303.0, 7531.2] | 0.818 [0.739, 0.900] | 0.818 |
| E6 Haiku 4.5 | API | 84.5 [80.5, 88.3] | 5918.7 [5026.7, 6861.0] | 5.228 [5.154, 5.299] | 5.228 |
| E5 Sonnet 5 | API | 84.1 [80.3, 87.8] | 10994.5 [9333.1, 13065.4] | 4.981 [4.909, 5.052] | 11.820 |
| E9 regex->Jev->Sonnet | API | 81.8 [77.8, 85.6] | 9892.1 [6902.6, 11874.4] | 0.989 [0.868, 1.116] | 1.351 |
| E8 regex->Sonnet | API | 81.5 [77.5, 85.3] | 7955.6 [7149.5, 14653.2] | 4.351 [4.258, 4.448] | 10.107 |
| E6b Qwen3-8B local | local | 79.9 [75.6, 84.0] | 11983.2 [10393.8, 12264.2] | 0.000 [0.000, 0.000] | 0.000 |
| E7 regex->Jev | API | 79.9 [75.8, 84.0] | 7128.9 [5785.1, 8469.8] | 0.727 [0.654, 0.805] | 0.727 |
| E10 classifier (probe) | local | 74.8 [70.2, 79.4] | 1048.1 [635.4, 4633.5] | 0.000 [0.000, 0.000] | 0.000 |
| E3 embedding (qwen3-emb 8B) | local | 73.6 [68.8, 78.2] | 710.2 [574.0, 1491.5] | 0.000 [0.000, 0.000] | 0.000 |
| E11 hybrid regex+classifier | local | 72.8 [67.9, 77.4] | 1036.7 [633.6, 4624.5] | 0.000 [0.000, 0.000] | 0.000 |
| E1 regex | local | 52.7 [47.3, 57.9] | 0.4 [0.3, 0.5] | 0.000 [0.000, 0.000] | 0.000 |
| E2 BM25 | local | 49.0 [43.8, 54.2] | 7.2 [5.6, 8.2] | 0.000 [0.000, 0.000] | 0.000 |

## Minimum joint accuracy 75%

| latency SLO \ cost ceiling | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 500 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 2000 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 10000 ms | none qualifies | none qualifies | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (also: E7, E9) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (also: E6, E7, E8, E9) |

## Minimum joint accuracy 80%

| latency SLO \ cost ceiling | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 500 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 2000 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 10000 ms | none qualifies | none qualifies | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (also: E9) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (also: E6, E8, E9) |

## Minimum joint accuracy 85%

| latency SLO \ cost ceiling | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 500 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 2000 ms | none qualifies | none qualifies | none qualifies | none qualifies |
| p95 < 10000 ms | none qualifies | none qualifies | none qualifies | none qualifies |

## Reading

- Highest joint point estimate among benchmarked configs: E4 Jev (84.7%).
- Best local (US$ 0) configuration: E6b Qwen3-8B local 79.9% at p95 11983 ms; best local under p95 2 s: E10 classifier (probe) 74.8% at p95 1048 ms.
- Cells marked `none qualifies` are a result (no benchmarked configuration meets all three constraints), not missing data.
