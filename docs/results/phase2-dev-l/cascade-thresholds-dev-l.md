# Cascade threshold calibration: freeze-dev-l-shadow-r1.jsonl

- source: freeze-dev-l-shadow-r1.jsonl (150 rows), dataset dataset_dev_l.jsonl b02b3722f5c4, scorer e0eef1fb0073, run git ['5d7ffc6']
- grid 0.50..0.99 (50 values) per non-last step; budget US$ 0.003761/case; 5-fold CV stratified by category over case ids, seed 0; rule (b) min support 5 accepted cases
- intention to treat: every row counts; a failed routing stage (error or parse failure) is WRONG, never an abstention, so a threshold cannot win by routing failing cases into an error; joint %: a tool stage that cannot be replayed (simulated skill differs from the recorded one) counted 0 (lower bound); US$/1k routing cost over covered rows; 95% CIs: cluster bootstrap over case ids (`eval/stats.py`, fixed seed)
- 'dev' = fitted and scored on all dev rows (optimistic); 'CV held-out' = re-fitted on k-1 folds, scored on the held-out fold, pooled
- confidences as recorded: 582/582 regex/BM25 decisions carry `usage.raw_confidence` (0 = the run predates the calibration maps: its thresholds are on the raw scale; re-run the shadow run with the current config before applying them)

## e7_regex_jev_l

skill: regex -> jev | tool: jev | 50 combos | 150 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 15 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.81 | - | 84.0 [78.0, 89.3] | 1.0077 [0.8434, 1.2052] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | regex=0.88 | - | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | 86.0 [80.0, 91.3] | 1.0390 [0.8746, 1.2340] | regex=0.89 / - x1; regex=0.88 / - x4 |
| (b) precision rule | regex=0.88 | - | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | 85.3 [79.3, 90.7] | 1.0405 [0.8728, 1.2390] | regex=0.88 / - x1; regex=0.89 / - x2; regex=0.67 / - x1; regex=0.81 / - x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 92.7% | 0.88 | 93.3% | 105 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 81.3 [74.7, 87.3] | 1.2966 [1.0890, 1.5400] |
| always-first (every step accepts any choice) | 80.0 [73.3, 86.0] | 0.9224 [0.7618, 1.1171] |
| oracle (best stopping step per row) | 88.0 [82.7, 92.7] | 0.8344 [0.6698, 1.0364] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 80.3 | 1.0214 |
| random deferral at (b) precision rule rates (200 draws, mean) | 80.3 | 1.0214 |

Pareto front on dev (7 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.65 | - | 80.0 | 83.3 | 0.9206 | 150 | 0 | 6 |
| regex=0.69 | - | 80.7 | 84.0 | 0.9212 | 150 | 0 | 6 |
| regex=0.72 | - | 81.3 | 84.7 | 0.9387 | 150 | 0 | 6 |
| regex=0.80 | - | 82.0 | 84.8 | 0.9743 | 150 | 0 | 5 |
| regex=0.83 | - | 84.0 | 85.1 | 1.0077 | 150 | 0 | 2 |
| regex=0.87 | - | 85.3 | 85.9 | 1.0120 | 150 | 0 | 1 |
| regex=0.88 | - | 86.7 | 86.7 | 1.0337 | 150 | 0 | 0 |

## e8_regex_llm_l

skill: regex -> llm | tool: llm | 50 combos | 150 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 11 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | infeasible | | | | | | |
| (b) precision rule | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | 82.7 [76.0, 88.7] | 6.4198 [5.9044, 6.9834] | regex=0.89 / - x3; regex=0.84 / - x1; regex=0.81 / - x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 92.7% | 0.88 | 93.3% | 105 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 80.0 [73.3, 86.0] | 7.5350 [6.9791, 8.1182] |
| always-first (every step accepts any choice) | 79.3 [72.7, 85.3] | 6.1567 [5.5918, 6.7548] |
| oracle (best stopping step per row) | 85.3 [79.3, 90.7] | 5.2436 [4.6846, 5.8456] |
| random deferral at (b) precision rule rates (200 draws, mean) | 79.5 | 6.5146 |

Pareto front on dev (4 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.58 | - | 79.3 | 83.8 | 6.1567 | 150 | 0 | 8 |
| regex=0.72 | - | 80.0 | 83.3 | 6.2390 | 150 | 0 | 6 |
| regex=0.80 | - | 80.7 | 83.4 | 6.3528 | 150 | 0 | 5 |
| regex=0.88 | - | 83.3 | 84.5 | 6.3995 | 150 | 0 | 2 |

## e9_regex_jev_llm_l

skill: regex -> jev -> llm | tool: jev -> llm | 125000 combos | 150 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 15 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.88, jev=0.76 | jev=0.50 | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | regex=0.88, jev=0.76 | jev=0.50 | 86.7 [80.7, 92.0] | 1.0337 [0.8686, 1.2304] | 86.0 [80.0, 91.3] | 1.0621 [0.8932, 1.2605] | regex=0.89, jev=0.76 / jev=0.50 x1; regex=0.88, jev=0.79 / jev=0.50 x1; regex=0.88, jev=0.76 / jev=0.50 x3 |
| (b) precision rule | regex=0.88, jev=0.93 | jev=0.50 | 85.3 [79.3, 90.7] | 1.3550 [1.1422, 1.5924] | 84.0 [78.0, 89.3] | 1.2172 [1.0117, 1.4497] | regex=0.88, jev=0.93 / jev=0.50 x1; regex=0.89, jev=0.88 / jev=0.50 x1; regex=0.89, jev=0.50 / jev=0.50 x1; regex=0.67, jev=never / jev=0.50 x1; regex=0.81, jev=0.93 / jev=0.50 x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 92.7% | 0.88 | 93.3% | 105 |
| skill | jev | 92.7% | 0.93 | 100.0% | 15 |
| tool | jev | 92.8% | 0.50 | 94.2% | 138 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 80.0 [73.3, 86.0] | 8.8178 [8.2118, 9.4285] |
| always-first (every step accepts any choice) | 80.0 [73.3, 86.0] | 0.9224 [0.7618, 1.1171] |
| oracle (best stopping step per row) | 88.7 [83.3, 93.3] | 1.0291 [0.8557, 1.2342] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 80.3 | 1.0178 |
| random deferral at (b) precision rule rates (200 draws, mean) | 80.2 | 1.3909 |

Pareto front on dev (7 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.65, jev=0.76 | jev=0.50 | 80.0 | 83.3 | 0.9206 | 150 | 0 | 6 |
| regex=0.69, jev=0.76 | jev=0.50 | 80.7 | 84.0 | 0.9212 | 150 | 0 | 6 |
| regex=0.72, jev=0.76 | jev=0.50 | 81.3 | 84.7 | 0.9387 | 150 | 0 | 6 |
| regex=0.80, jev=0.76 | jev=0.50 | 82.0 | 84.8 | 0.9743 | 150 | 0 | 5 |
| regex=0.83, jev=0.76 | jev=0.50 | 84.0 | 85.1 | 1.0077 | 150 | 0 | 2 |
| regex=0.87, jev=0.76 | jev=0.50 | 85.3 | 85.9 | 1.0120 | 150 | 0 | 1 |
| regex=0.88, jev=0.76 | jev=0.50 | 86.7 | 86.7 | 1.0337 | 150 | 0 | 0 |

## e12_hybrid_jev_llm_l

skill: hybrid -> jev -> llm | tool: jev -> llm | 125000 combos | 150 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 11 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | hybrid=0.83, jev=0.77 | jev=0.50 | 82.7 [76.0, 88.0] | 1.0560 [0.8731, 1.2660] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | hybrid=0.78, jev=0.76 | jev=0.50 | 84.0 [78.0, 89.3] | 0.9763 [0.8130, 1.1734] | 82.7 [76.0, 88.7] | 1.0689 [0.8776, 1.2904] | hybrid=0.78, jev=0.76 / jev=0.50 x1; hybrid=0.78, jev=0.79 / jev=0.50 x1; hybrid=0.78, jev=0.76 / jev=0.55 x1; hybrid=0.93, jev=0.76 / jev=0.50 x1; hybrid=0.77, jev=0.76 / jev=0.50 x1 |
| (b) precision rule | hybrid=0.70, jev=never | jev=0.50 | 82.7 [76.0, 88.7] | 1.1629 [0.9705, 1.3832] | 80.7 [74.0, 86.7] | 1.1647 [0.9656, 1.3861] | hybrid=0.70, jev=never / jev=0.50 x1; hybrid=0.77, jev=0.93 / jev=0.50 x1; hybrid=0.85, jev=never / jev=0.50 x1; hybrid=0.52, jev=never / jev=0.50 x1; hybrid=0.50, jev=never / jev=0.50 x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | hybrid | 92.7% | 0.70 | 93.3% | 134 |
| skill | jev | 92.7% | never (drop step) | - | 0 |
| tool | jev | 92.8% | 0.50 | 94.2% | 138 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 80.0 [73.3, 86.0] | 8.8178 [8.2118, 9.4285] |
| always-first (every step accepts any choice) | 80.0 [73.3, 86.0] | 0.9656 [0.7992, 1.1721] |
| oracle (best stopping step per row) | 88.0 [82.7, 92.7] | 1.0046 [0.8383, 1.2062] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 80.2 | 1.0337 |
| random deferral at (b) precision rule rates (200 draws, mean) | 80.0 | 1.2002 |

Pareto front on dev (3 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| hybrid=0.71, jev=0.76 | jev=0.50 | 82.7 | 86.1 | 0.9533 | 150 | 0 | 6 |
| hybrid=0.77, jev=0.76 | jev=0.50 | 83.3 | 86.8 | 0.9729 | 150 | 0 | 6 |
| hybrid=0.78, jev=0.76 | jev=0.50 | 84.0 | 87.5 | 0.9763 | 150 | 0 | 6 |
