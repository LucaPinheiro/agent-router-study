# Tuning effort, phase 2 (dev / dev-L only)

Same protocol as phase 1 (`docs/tuning-effort.md`): 5-fold CV stratified by category, seed 0
(`scripts/analysis/tune_router.py`). "Nested" = per fold, the grid point that is best on the other
4 folds is scored on the held-out fold (an estimate of the tuning procedure). "Fixed" = the
committed config scored on all dev (chosen on the same data, optimistic). CIs are the paired
case bootstrap of prereg-v1 (10,000 resamples, seed 20260930) over the pooled held-out rows.
Calibration maps are fitted on train folds and scored on the held-out fold; with
`--calibrator both` the map (isotonic or Platt) is chosen per level by the pooled held-out Brier,
and it is **written into the config only if its cross-fitted ECE is lower than the raw ECE**
(`docs/decisions/2026-10-01-calibration-and-prompts.md`, prereg-v2 §5). The test splits were
never read.

## §A. Part A: cloud addendum on the 18-tool catalog (phase-1 dev, 151 cases)

Only the six new strategies are tuned; every phase-1 strategy is reused as frozen. Logs and
per-point JSON: `results/phase2a/` (gitignored); the summary JSONs are copied to
`docs/results/addendum-dev/`. Phase-2 constraint: no local model was run for any of this.

### Effort ledger

| strategy | configs evaluated | dev passes | wall-clock | paid calls | notes |
|---|---|---|---|---|---|
| E3c Cohere Embed v4 | 324 (phase-1 D1 grid, verbatim) + 3 (T by calibrated Brier) + 1 final `study run` = 328 | 328 (9 distinct query texts × 151 embedded once; vector cache) | ~3 min | ~US$ 0.004 | Grid script `results/phase2a/emb_grid.sh` = `results/phase2/emb_grid1.sh` with the config swapped. The Qwen-style instruction prefixes of the grid are kept as-is (same grid); Cohere also gets its own `input_type` (search_query / search_document). |
| E3t Titan v2 | 324 + 3 + 1 = 328 | 328 | ~1.5 min | ~US$ 0.001 | As E3c. |
| E10c probe on Cohere | 64 (phase-1 D4 probe grid) + 8 (C × history refinement around the 64-grid best: C ∈ {0.1, 0.3, 1, 3} × best C, other axes at the 64-grid best) + 1 final + 1 `study run` = 74 | 74 | ~30 s | < US$ 0.001 | Phase-1 refinement was {0.1, 0.3, 1, 3} around best C = 1; the same ratios are used around this model's best C (100 → {10, 30, 100, 300}). |
| E10t probe on Titan | 64 + 8 (best C = 1 → {0.1, 0.3, 1, 3}) + 1 + 1 = 74 | 74 | ~30 s | < US$ 0.001 | As E10c. |
| E6m Ministral 3 8B | 1 (P0 only; no prompt search) + calibration | 1 (the coordinator's dev run, response cache) | – | ~US$ 0.07 (dev run) | Isotonic maps (the phase-1 LLM procedure, `select_prompts.py`). |
| E6n Nemotron Nano 9B v2 | 1 (P0, `/no_think`) + calibration | 1 | – | ~US$ 0.03 (dev run) | As E6m. |

Human/agent time: about 1 h of agent time for all six, mostly waiting on the two grids. No rule
writing, no reading of dev errors to edit anything: every choice is a grid argmax or the
pre-declared calibration rule.

### Before → after (dev, 5-fold CV)

skill/tool are the fixed config on all dev. ECE and Brier read raw → calibrated (cross-fitted).
p50/p95 are ms per case (skill + tool stage) as recorded on dev, where Bedrock calls ran at
concurrency 2 from the Mac in São Paulo to `sa-east-1`: **not** the benchmark latency (that
comes only from the `lat-a-*` blocks of `config/addendum_manifest.yaml`).

| router | config | skill | tool | joint fixed [95% CI] | joint nested [95% CI] | skill ECE / Brier | tool ECE / Brier | map written | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| E3c Cohere v4 | before (first grid point: max_example, T 0.02, no history, no shots, no instruction) | 62.3 | 47.7 | 47.7 | – | 0.219 (raw) | 0.353 (raw) | – | 570 / 1424 |
| E3c Cohere v4 | **after**: topk_vote k 5, T 0.1, history 2, shots, no instruction | 73.5 | 62.9 | 62.9 [55.0, 70.9] | **59.6 [51.7, 67.5]** | 0.069→0.047 / 0.167→0.169 (Platt) | 0.120→0.050 / 0.224→0.207 (isotonic) | skill + tool | 562 / 1382 |
| E3t Titan v2 | before (same baseline point) | 58.9 | 45.0 | 44.4 | – | 0.215 (raw) | 0.367 (raw) | – | 138 / 358 |
| E3t Titan v2 | **after**: centroid, T 0.02, history 1, shots, no instruction | 73.5 | 61.6 | 60.3 [52.3, 68.2] | **60.3 [52.3, 68.2]** | 0.094→0.070 / 0.172→0.172 (isotonic) | 0.225→0.061 / 0.233→0.183 (Platt) | skill + tool | 136 / 226 |
| E10c probe (Cohere) | **after**: C 10, shots, description, no instruction, history 0 | 68.9 | 60.9 | 57.0 [49.0, 64.9] | **53.6 [45.7, 61.6]** (64-pt) / 56.3 [48.3, 64.2] (refinement) | 0.103→0.103 / 0.200→0.192 (isotonic) | 0.230→0.121 / 0.256→0.198 (isotonic) | tool only (skill ECE 0.1027→0.1028: not lower) | 568 / 1359 |
| E10t probe (Titan) | **after**: C 0.1, shots, description, no instruction, history 0 | 70.9 | 62.3 | 60.9 [53.0, 68.2] | **60.9 [53.0, 68.9]** (64-pt) / 59.0 [51.0, 66.9] (refinement) | 0.441→0.070 / 0.397→0.179 (isotonic) | 0.440→0.219 / 0.454→0.234 (isotonic) | skill + tool | 135 / 215 |
| E6m Ministral 3 8B | P0, T 0 | 88.7 | 80.8 | 79.5 [72.8, 86.1] (CV); 78.8 [72.2, 85.4] in the `study run` ITT (1 error row, recovered on a later retry) | = fixed (one point) | 0.093→0.041 / 0.104→0.089 (isotonic) | 0.142→0.029 / 0.170→0.144 (isotonic) | skill + tool | 1008 / 1174 |
| E6n Nemotron Nano 9B v2 | P0, T 0, `/no_think` | 86.8 | 78.8 | 78.1 [71.5, 84.8] | = fixed (one point) | 0.061→0.012 / 0.106→0.103 (isotonic) | 0.146→0.092 / 0.177→0.162 (isotonic) | skill + tool | 1553 / 2310 |

Phase-1 local peers on the same dev (from `docs/tuning-effort.md` and `config/prompt_selection.yaml`):
qwen3-embedding 8B E3 nested 77.5, local probe E10 76.2–76.8, Qwen3-8B E6b 82.2 (CV).

### 8B routers: full-P0 cost and parse-failure check (T0.3 / T2.3)

| model | prompt tokens per call (mean) | output tokens per call | US$ per 1k cases (skill + tool) | parse failures (calls) | error rows (ITT, wrong) |
|---|---|---|---|---|---|
| Ministral 3 8B | 1,167 | 79 | 0.449 | 1 / 302 (0.3%) on the first pass; 0 after the retry | 1 / 151 (0.7%) → 0 |
| Nemotron Nano 9B v2 | 1,340 | 69 | 0.226 | 2 / 302 (0.7%) | 2 / 151 (1.3%) |

Both are under the 2% threshold, so **no format-only fix** was applied. The real P0 prompt is
about 1.2–1.3k tokens per call, not the 2.3k assumed in plan §5: the plan's per-case estimate
(Ministral 0.00085, Nemotron 0.00035) is about 2× / 1.5× too high, so A3 (test-v2 8B ×2, 399
cases) is about US$ 0.27 instead of 0.50.

### What moved the numbers

- **Managed embedders are far below the local qwen3-embedding 8B on this task** (nested 59.6 /
  60.3 vs 77.5). The gap is in both stages and largest in `fora_escopo` for Cohere (13% joint).
- Shots are selected for both embedders (as for qwen3); history helps (Cohere 2 turns, Titan 1).
- No instruction prefix wins for either: the Qwen-style `Instruct: …\nQuery:` prefix costs both
  models 5–15 points. That is expected (they are not instruction-tuned that way); the grid was
  kept identical to phase 1 on purpose.
- Cohere prefers kNN voting (`topk_vote`, k 5) over centroid, unlike qwen3 and Titan.
- The probes do not beat their own embedding router (E10c 53.6–56.3 vs E3c 59.6; E10t 59.0–60.9
  vs E3t 60.3), unlike the local probe, which matched the local router.
- The managed 8B LLMs land within 3–4 points of the local Qwen3-8B on dev (79.5 / 78.1 vs 82.2);
  family A tests that gap on test-v2 with a 3 pp NI margin.
