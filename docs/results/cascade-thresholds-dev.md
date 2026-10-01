# Cascade threshold calibration: freeze-dev-shadow-r1.jsonl

- source: freeze-dev-shadow-r1.jsonl (151 rows), dataset dataset_dev.jsonl 112fc7f0791e, scorer e0eef1fb0073, run git ['b76b3b1-dirty.42b16ddf']
- grid 0.50..0.99 (50 values) per non-last step; budget US$ 0.0029875/case; 5-fold CV stratified by category over case ids, seed 0; rule (b) min support 5 accepted cases
- intention to treat: every row counts; a failed routing stage (error or parse failure) is WRONG, never an abstention, so a threshold cannot win by routing failing cases into an error; joint %: a tool stage that cannot be replayed (simulated skill differs from the recorded one) counted 0 (lower bound); US$/1k routing cost over covered rows; 95% CIs: cluster bootstrap over case ids (`eval/stats.py`, fixed seed)
- 'dev' = fitted and scored on all dev rows (optimistic); 'CV held-out' = re-fitted on k-1 folds, scored on the held-out fold, pooled
- confidences as recorded: 564/564 regex/BM25 decisions carry `usage.raw_confidence` (0 = the run predates the calibration maps: its thresholds are on the raw scale; re-run the shadow run with the current config before applying them)

## e7_regex_jev

skill: regex -> jev | tool: jev | 50 combos | 151 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 11 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.90 | - | 79.5 [72.8, 85.4] | 0.8922 [0.7571, 1.0396] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | regex=0.81 | - | 79.5 [72.8, 85.4] | 0.8626 [0.7270, 1.0076] | 78.8 [72.2, 85.4] | 0.8647 [0.7277, 1.0138] | regex=0.81 / - x3; regex=0.88 / - x1; regex=0.83 / - x1 |
| (b) precision rule | regex=0.62 | - | 76.2 [69.5, 82.8] | 0.8185 [0.6830, 0.9622] | 76.2 [68.9, 82.8] | 0.8180 [0.6825, 0.9676] | regex=0.50 / - x2; regex=0.70 / - x2; regex=0.62 / - x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 76.8 [69.5, 83.4] | 0.9385 [0.8008, 1.0824] |
| always-first (every step accepts any choice) | 75.5 [68.2, 82.1] | 0.8188 [0.6822, 0.9675] |
| oracle (best stopping step per row) | 80.8 [74.2, 86.8] | 0.5663 [0.4705, 0.6735] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 75.9 | 0.8537 |
| random deferral at (b) precision rule rates (200 draws, mean) | 75.5 | 0.8205 |

Pareto front on dev (3 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.63 | - | 76.2 | 77.7 | 0.8185 | 151 | 0 | 3 |
| regex=0.74 | - | 78.8 | 79.3 | 0.8414 | 151 | 0 | 1 |
| regex=0.81 | - | 79.5 | 80.0 | 0.8626 | 151 | 0 | 1 |

## e8_regex_llm

skill: regex -> llm | tool: llm | 50 combos | 151 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 12 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.90 | - | 78.1 [71.5, 84.8] | 5.2076 [4.8329, 5.6168] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | infeasible | | | | | | |
| (b) precision rule | regex=0.62 | - | 74.8 [68.2, 81.5] | 4.6778 [4.3297, 5.0525] | 74.2 [66.9, 80.8] | 4.6793 [4.3342, 5.0586] | regex=0.50 / - x2; regex=0.62 / - x2; regex=0.70 / - x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 76.8 [69.5, 83.4] | 5.9150 [5.5388, 6.3098] |
| always-first (every step accepts any choice) | 74.2 [66.9, 80.8] | 4.6557 [4.3083, 5.0338] |
| oracle (best stopping step per row) | 80.1 [73.5, 86.1] | 3.7123 [3.3645, 4.0834] |
| random deferral at (b) precision rule rates (200 draws, mean) | 74.2 | 4.6739 |

Pareto front on dev (5 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.50 | - | 74.2 | 75.7 | 4.6557 | 151 | 0 | 3 |
| regex=0.63 | - | 74.8 | 76.4 | 4.6778 | 151 | 0 | 3 |
| regex=0.74 | - | 77.5 | 78.0 | 4.7724 | 151 | 0 | 1 |
| regex=0.81 | - | 78.1 | 78.7 | 5.0228 | 151 | 0 | 1 |
| regex=0.88 | - | 78.8 | 79.3 | 5.1690 | 151 | 0 | 1 |

## e9_regex_jev_llm

skill: regex -> jev -> llm | tool: jev -> llm | 125000 combos | 151 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 12 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.90, jev=0.75 | jev=0.70 | 80.1 [73.5, 86.1] | 2.3486 [1.8473, 2.8776] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | regex=0.88, jev=0.76 | jev=0.50 | 80.1 [73.5, 86.1] | 1.2046 [0.9512, 1.4858] | 77.5 [70.9, 84.1] | 1.2761 [0.9932, 1.5996] | regex=0.81, jev=0.73 / jev=0.50 x1; regex=0.88, jev=0.73 / jev=0.65 x1; regex=0.88, jev=0.76 / jev=0.50 x3 |
| (b) precision rule | regex=0.62, jev=0.50 | jev=0.50 | 76.2 [69.5, 82.8] | 0.9421 [0.7316, 1.1879] | 76.2 [68.9, 82.8] | 0.9416 [0.7344, 1.1868] | regex=0.50, jev=0.50 / jev=0.50 x2; regex=0.70, jev=0.50 / jev=0.50 x2; regex=0.62, jev=0.50 / jev=0.50 x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |
| skill | jev | 91.4% | 0.50 | 94.4% | 18 |
| tool | jev | 83.2% | 0.50 | 86.3% | 139 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 76.8 [69.5, 83.4] | 6.8631 [6.4352, 7.3162] |
| always-first (every step accepts any choice) | 75.5 [68.2, 82.1] | 0.8188 [0.6822, 0.9675] |
| oracle (best stopping step per row) | 83.4 [77.5, 89.4] | 0.8758 [0.7410, 1.0227] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 76.1 | 1.1133 |
| random deferral at (b) precision rule rates (200 draws, mean) | 75.5 | 0.9419 |

Pareto front on dev (4 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.63, jev=0.73 | jev=0.50 | 76.2 | 77.7 | 0.9421 | 151 | 0 | 3 |
| regex=0.74, jev=0.73 | jev=0.50 | 78.8 | 79.3 | 0.9607 | 151 | 0 | 1 |
| regex=0.81, jev=0.73 | jev=0.50 | 79.5 | 80.0 | 0.9811 | 151 | 0 | 1 |
| regex=0.88, jev=0.76 | jev=0.50 | 80.1 | 80.7 | 1.2046 | 151 | 0 | 1 |

## e12_hybrid_jev_llm

skill: hybrid -> jev -> llm | tool: jev -> llm | 125000 combos | 151 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 11 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | hybrid=0.90, jev=0.75 | jev=0.70 | 79.5 [72.8, 85.4] | 2.1950 [1.7153, 2.7108] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | hybrid=0.83, jev=0.77 | jev=0.50 | 80.1 [73.5, 86.1] | 1.0209 [0.7912, 1.2866] | 78.1 [71.5, 84.8] | 1.1910 [0.9230, 1.4884] | hybrid=0.81, jev=0.73 / jev=0.50 x1; hybrid=0.83, jev=0.77 / jev=0.65 x1; hybrid=0.83, jev=0.77 / jev=0.50 x2; hybrid=0.83, jev=0.80 / jev=0.50 x1 |
| (b) precision rule | hybrid=0.50, jev=never | jev=0.50 | 77.5 [70.9, 84.1] | 0.9075 [0.7010, 1.1565] | 77.5 [70.9, 84.1] | 0.9075 [0.7010, 1.1565] | hybrid=0.50, jev=never / jev=0.50 x5 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | hybrid | 91.4% | 0.50 | 93.4% | 151 |
| skill | jev | 91.4% | never (drop step) | - | 0 |
| tool | jev | 83.2% | 0.50 | 86.3% | 139 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 76.8 [69.5, 83.4] | 6.8631 [6.4352, 7.3162] |
| always-first (every step accepts any choice) | 77.5 [70.9, 84.1] | 0.7865 [0.6522, 0.9351] |
| oracle (best stopping step per row) | 83.4 [77.5, 89.4] | 0.8254 [0.6921, 0.9697] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 77.4 | 0.9812 |
| random deferral at (b) precision rule rates (200 draws, mean) | 77.5 | 0.9060 |

Pareto front on dev (3 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| hybrid=0.79, jev=0.73 | jev=0.50 | 78.8 | 79.9 | 0.9046 | 151 | 0 | 2 |
| hybrid=0.81, jev=0.73 | jev=0.50 | 79.5 | 80.5 | 0.9073 | 151 | 0 | 2 |
| hybrid=0.83, jev=0.77 | jev=0.50 | 80.1 | 81.2 | 1.0209 | 151 | 0 | 2 |
## E8 fallback (budget infeasible): Cascade threshold calibration: freeze-dev-shadow-r1.jsonl

- source: freeze-dev-shadow-r1.jsonl (151 rows), dataset dataset_dev.jsonl 112fc7f0791e, scorer e0eef1fb0073, run git ['b76b3b1-dirty.42b16ddf']
- grid 0.50..0.99 (50 values) per non-last step; budget none (max joint accuracy); 5-fold CV stratified by category over case ids, seed 0; rule (b) min support 5 accepted cases
- intention to treat: every row counts; a failed routing stage (error or parse failure) is WRONG, never an abstention, so a threshold cannot win by routing failing cases into an error; joint %: a tool stage that cannot be replayed (simulated skill differs from the recorded one) counted 0 (lower bound); US$/1k routing cost over covered rows; 95% CIs: cluster bootstrap over case ids (`eval/stats.py`, fixed seed)
- 'dev' = fitted and scored on all dev rows (optimistic); 'CV held-out' = re-fitted on k-1 folds, scored on the held-out fold, pooled
- confidences as recorded: 564/564 regex/BM25 decisions carry `usage.raw_confidence` (0 = the run predates the calibration maps: its thresholds are on the raw scale; re-run the shadow run with the current config before applying them)

## e8_regex_llm

skill: regex -> llm | tool: llm | 50 combos | 151 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 13 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.90 | - | 78.1 [71.5, 84.8] | 5.2076 [4.8329, 5.6168] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | regex=0.88 | - | 78.8 [72.2, 85.4] | 5.1690 [4.7919, 5.5812] | 78.1 [71.5, 84.8] | 5.1382 [4.7505, 5.5640] | regex=0.81 / - x1; regex=0.88 / - x4 |
| (b) precision rule | regex=0.62 | - | 74.8 [68.2, 81.5] | 4.6778 [4.3297, 5.0525] | 74.2 [66.9, 80.8] | 4.6793 [4.3342, 5.0586] | regex=0.50 / - x2; regex=0.62 / - x2; regex=0.70 / - x1 |

Rule (b) on all dev rows:

| stage | step | target = next step's precision | threshold | precision of accepted | accepted n |
|---|---|---|---|---|---|
| skill | regex | 91.4% | 0.62 | 91.7% | 133 |

References on dev (all rows, no fit):

| reference | joint % [95% CI] | US$/1k routing [95% CI] |
|---|---|---|
| always-last (final router alone) | 76.8 [69.5, 83.4] | 5.9150 [5.5388, 6.3098] |
| always-first (every step accepts any choice) | 74.2 [66.9, 80.8] | 4.6557 [4.3083, 5.0338] |
| oracle (best stopping step per row) | 80.1 [73.5, 86.1] | 3.7123 [3.3645, 4.0834] |
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 75.2 | 5.1449 |
| random deferral at (b) precision rule rates (200 draws, mean) | 74.2 | 4.6739 |

Pareto front on dev (5 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.50 | - | 74.2 | 75.7 | 4.6557 | 151 | 0 | 3 |
| regex=0.63 | - | 74.8 | 76.4 | 4.6778 | 151 | 0 | 3 |
| regex=0.74 | - | 77.5 | 78.0 | 4.7724 | 151 | 0 | 1 |
| regex=0.81 | - | 78.1 | 78.7 | 5.0228 | 151 | 0 | 1 |
| regex=0.88 | - | 78.8 | 79.3 | 5.1690 | 151 | 0 | 1 |
