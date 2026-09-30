# Cascade threshold calibration

`projeto.md`: *"Limiares são por estratégia e por estágio, e vêm da calibração no split de
desenvolvimento, nunca de chute."* This is the tool that produces them.

```bash
uv run study rescore results/<shadow-dev-run>.jsonl --out results/rescored
uv run python scripts/analysis/calibrate_cascades.py results/rescored/<shadow-dev-run>.jsonl \
    [--config config/experiments/e9_regex_jev_llm.yaml ...] [--budget 0.0008] \
    [--folds 5] [--seed 0] [--grid 0.50 0.99 0.01] [--min-support 5] \
    [--out-dir results/calibration]
```

- **Input:** a *rescored* shadow run (`--routing-mode shadow`) on the **dev** split; the
  script refuses any other split. A shadow row holds every strategy's decision for both
  stages, so any cascade can be replayed offline for any threshold. No API call is made.
- **Cascades:** E7, E8 and E9 by default; `--config` replaces the list (any cascade whose
  strategies were recorded in the shadow run). Tuned: the `min_confidence` of every step but
  the last, per stage (the last step keeps its configured rule, normally "accept any choice").
- **Output** (`--out-dir`): `calibration.md` (report), `thresholds.yaml` (a `routing:`
  snippet per experiment and method, **not** applied to `config/experiments`: copy the
  chosen block by hand) and `pareto.csv` (accuracy-vs-cost front per experiment, for plots).

## Methods

**(a) Budget / Pareto.** Every combination on the grid (default 0.50..0.99, step 0.01, per
tuned step: 50 combos for E7/E8, 50² × 50 = 125 000 for E9) is replayed. Pick: max joint
accuracy subject to routing cost/case ≤ `--budget` (no budget: max joint accuracy); ties go
to the lower cost, then to the higher thresholds. The report and `pareto.csv` also list the
whole non-dominated front (cost ↑, accuracy ↑), so a different budget can be read off it.

**(b) Precision rule** (easy to explain). Step by step, in pipeline order: accept a cheap
step at the **lowest** grid threshold where its precision on the cases it accepts (among the
cases reaching it) is ≥ the next step's overall precision (over every fit case where the next
step chose), with at least `--min-support` accepted cases. If no threshold qualifies the step
is marked `never`: it should be dropped (the YAML snippet leaves it out). Precision is
`skill_can_be_correct` for the skill stage and joint correctness given the recorded skill for
the tool stage (tool decisions are only scorable when the recorded skill could be right).

## Keeping the choice honest

- **Same scorer, same simulator.** Scoring uses the shared functions of `eval/scorers.py`
  (`routing_scores`, `skill_can_be_correct`, `routing_failure`), with the rules of
  `eval/simulate.simulate_rows`: error rows excluded, a wrong skill scores 0, a tool stage
  that cannot be replayed (the simulated skill differs from the recorded one) counts 0 (lower
  bound, `unavail`), cost over covered rows. The grid is evaluated by a vectorised path
  (`eval/calibrate.py`) for speed, and **every reported point** (configured, (a), (b), every
  Pareto point and `--checks` random combos) is re-run through `simulate_rows` and must match
  exactly, or the script fails.
- **Fixed denominator.** A row that is an error row at *some* grid point (a consulted step
  failed and nothing accepted) is dropped for that experiment. Otherwise a threshold could
  look better by escalating hard cases to a step that failed on them (error rows leave the
  accuracy denominator). The report says how many rows were dropped.
- **Cross-validation.** Stratified k-fold (by category, over case ids, fixed seed; the same
  algorithm as `scripts/analysis/tune_router.py`, so the same folds for the same case set). Each method is re-fitted on k-1 folds and
  scored on the held-out fold; the pooled held-out rows give joint accuracy and cost with 95%
  cluster-bootstrap CIs (`eval/stats.bootstrap_mean`, resampling case ids). The per-fold picks
  show how stable the choice is. "dev" columns are fitted and scored on the same rows
  (optimistic); quote the CV column.

## Caveats

- Thresholds live on the confidence scale **recorded** in the shadow run. The report counts
  how many regex/BM25 decisions carry `usage.raw_confidence`; `0` means the run predates the
  calibration maps and its thresholds are on the raw scale: re-run the shadow run with the
  current configs before applying them.
- The tool stage was recorded for the skill the shadow run's own pipeline chose. Thresholds
  that change a wrong recorded skill into a right one cannot replay the tool stage and are
  counted 0, which biases the search slightly towards the recorded thresholds; `joint cov.`
  (Pareto table) excludes those rows.
- With ~150 dev cases the CIs are wide (±7 pp): differences between methods inside the CIs are
  not evidence. Rule (b) is especially unstable per fold at small support.

## Example (dev shadow run of 2026-09-29, `docs/results/shadow-dev-routing-only.jsonl`)

Rescored into `/tmp` and calibrated with the defaults (no budget). E9 (regex → jev → llm for
the skill, jev → llm for the tool); 135 of 151 rows are error-free at every grid point:

| method | skill thresholds | tool thresholds | dev joint % | CV held-out joint % [95% CI] | CV US$/1k routing [95% CI] |
|---|---|---|---|---|---|
| configured (YAML) | regex=0.90, jev=0.75 | jev=0.70 | 78.5 | = dev (no fit) | 0.597 [0.428, 0.788] |
| (a) max joint | regex=0.89, jev=0.60 | jev=0.99 | 80.7 | 79.3 [71.9, 85.9] | 1.576 [1.280, 1.897] |
| (b) precision rule | regex=0.71, jev=0.92 | jev=0.74 | 78.5 | 77.8 [70.4, 84.4] | 1.023 [0.798, 1.268] |

The E9 Pareto front shows the trade-off: the tool-stage jev threshold buys +2.2 pp joint
(78.5 → 80.7) for ~4× the routing cost (0.39 → 1.63 US$/1k), all inside the CI. This run
predates the regex/BM25 calibration maps (0/405 decisions carry `raw_confidence`), so these
numbers illustrate the tool; re-run the dev shadow run before applying any threshold.
