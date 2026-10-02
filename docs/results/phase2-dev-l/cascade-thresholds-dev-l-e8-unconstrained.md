# Cascade threshold calibration: freeze-dev-l-shadow-r1.jsonl

- source: freeze-dev-l-shadow-r1.jsonl (150 rows), dataset dataset_dev_l.jsonl b02b3722f5c4, scorer e0eef1fb0073, run git ['5d7ffc6']
- grid 0.50..0.99 (50 values) per non-last step; budget none (max joint accuracy); 5-fold CV stratified by category over case ids, seed 0; rule (b) min support 5 accepted cases
- intention to treat: every row counts; a failed routing stage (error or parse failure) is WRONG, never an abstention, so a threshold cannot win by routing failing cases into an error; joint %: a tool stage that cannot be replayed (simulated skill differs from the recorded one) counted 0 (lower bound); US$/1k routing cost over covered rows; 95% CIs: cluster bootstrap over case ids (`eval/stats.py`, fixed seed)
- 'dev' = fitted and scored on all dev rows (optimistic); 'CV held-out' = re-fitted on k-1 folds, scored on the held-out fold, pooled
- confidences as recorded: 582/582 regex/BM25 decisions carry `usage.raw_confidence` (0 = the run predates the calibration maps: its thresholds are on the raw scale; re-run the shadow run with the current config before applying them)

## e8_regex_llm_l

skill: regex -> llm | tool: llm | 50 combos | 150 rows (0 excluded as ever-error) | fast evaluator == simulate_rows at 12 points

| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k | CV held-out joint % | CV US$/1k | picks per fold |
|---|---|---|---|---|---|---|---|
| configured (YAML) | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | = dev (no fit) | = dev | (no fit) |
| (a) max joint s.t. budget | regex=0.88 | - | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | 83.3 [77.3, 88.7] | 6.3995 [5.8983, 6.9404] | regex=0.88 / - x5 |
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
| random deferral at (a) max joint s.t. budget rates (200 draws, mean) | 79.5 | 6.5146 |
| random deferral at (b) precision rule rates (200 draws, mean) | 79.5 | 6.5146 |

Pareto front on dev (4 points; pareto.csv):

| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k | n | err | unavail |
|---|---|---|---|---|---|---|---|
| regex=0.58 | - | 79.3 | 83.8 | 6.1567 | 150 | 0 | 8 |
| regex=0.72 | - | 80.0 | 83.3 | 6.2390 | 150 | 0 | 6 |
| regex=0.80 | - | 80.7 | 83.4 | 6.3528 | 150 | 0 | 5 |
| regex=0.88 | - | 83.3 | 84.5 | 6.3995 | 150 | 0 | 2 |
