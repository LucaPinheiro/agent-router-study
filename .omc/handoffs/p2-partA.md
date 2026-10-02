# Handoff: phase 2 Part A (T2.1 check, T2.2, T2.3, T2.4 prepared)

Branch `feat/phase2-cloud-and-large-catalog`. Nothing was run on test-v2 (the manifest dry-run only
lists the 349 test-v2 ids). No tag was created. No local model was run.

## Done

- **T2.1 remaining check.** Every phase-1 manifest entry (study + explore, 104) reproduces its
  frozen `config_hash` / `prompt_hash` on top of ac6c67b + 5d788f5; `scorer_hash` e0eef1fb0073,
  `prompt_hash` c61ad0a7b7f8. (`tests/test_phase1_hashes.py`, T0.1, does not exist yet: still owed.)
- **T2.2 configs** (one source of truth, the plan's ids):
  - `config/experiments/e6m_llm_ministral.yaml`, `e6n_llm_nemotron.yaml` (renamed from the
    coordinator's `e6c_llm_ministral_bedrock.yaml` / `e6d_llm_nemotron_bedrock.yaml`; they use the
    `llm` block on Bedrock, not an extra `llm_<suffix>` block). The old dev result files keep their
    old run names (`results/p2-dev-e6c_*`, `p2-dev-e6d_*`).
  - `e3_embedding_cohere.yaml`, `e3_embedding_titan.yaml`, `e10_classifier_cohere.yaml`,
    `e10_classifier_titan.yaml`: minimal configs (only the blocks the pipeline uses + executor).
  - `tests/routers/test_settings_tracing.py`: `test_all_experiments_load` now allows e6m/e6n and
    skips the Part-A configs; new `test_part_a_configs`.
- **T2.3 dev tuning** (phase-1 dev, 151; `docs/tuning-effort-l.md` §A; logs `results/phase2a/`,
  summaries copied to `docs/results/addendum-dev/`):
  - E3c/E3t: phase-1 D1 324-point grid verbatim (`emb_grid.sh`), then T by calibrated Brier.
  - E10c/E10t: phase-1 D4 64-point probe grid + 8-point C × history refinement (same ratios around
    each model's best C), final = refinement best (as phase 1).
  - E6m/E6n: P0 only, isotonic maps (phase-1 LLM procedure). Parse failures < 2%: no format fix.
  - Maps written only where cross-fitted ECE < raw (E10c skill: not written).
  - `scripts/analysis/tune_router.py`: prints and stores (`nested_joint_pooled_ci`) the case
    bootstrap CI of the pooled held-out joint. Additive only.
  - `study run --split dev --mode routing-only` with the frozen configs reproduces the fixed numbers
    (`results/p2a-dev-*`): E3c 62.9, E3t 60.3, E10c 57.0, E10t 60.9, E6m 78.8 (1 error row, ITT),
    E6n 78.1; all rows catalog 128584617807.
- **T2.4 prepared:** `config/addendum_manifest.yaml` (hashes frozen with `prereg_hashes.py`,
  dry-run: 40 PLAN, 0 ABORT) and `docs/prereg/prereg-v2a.md` (frozen hashes, family A, estimation,
  budget, caveats). `prereg-v2-draft.md` Part A text updated for the no-local constraint.

## Dev results (5-fold CV, seed 0)

| arm | joint nested [95% CI] | fixed | skill ECE raw→cal | tool ECE raw→cal | p50 / p95 ms (dev, not benchmark) |
|---|---|---|---|---|---|
| E3c Cohere v4 | 59.6 [51.7, 67.5] | 62.9 | 0.069→0.047 | 0.120→0.050 | 562 / 1382 |
| E3t Titan v2 | 60.3 [52.3, 68.2] | 60.3 | 0.094→0.070 | 0.225→0.061 | 136 / 226 |
| E10c probe Cohere | 53.6 [45.7, 61.6] (64-pt), 56.3 (refine) | 57.0 | 0.103 (no map) | 0.230→0.121 | 568 / 1359 |
| E10t probe Titan | 60.9 [53.0, 68.9] (64-pt), 59.0 (refine) | 60.9 | 0.441→0.070 | 0.440→0.219 | 135 / 215 |
| E6m Ministral 3 8B | 79.5 [72.8, 86.1] | 79.5 | 0.093→0.041 | 0.142→0.029 | 1008 / 1174 |
| E6n Nemotron 9B v2 | 78.1 [71.5, 84.8] | 78.1 | 0.061→0.012 | 0.146→0.092 | 1553 / 2310 |

Local peers (phase 1, dev): E3 qwen3-embedding 77.5, E10 local probe 76.2–76.8, E6b Qwen3-8B 82.2.

## Spend

AWS ledger 52.2902 → 52.2987 during this work (≈ US$ 0.009, embeddings + a few 8B retries; part of
it may be other workers). OpenRouter unchanged (5.8395). Phase-2 AWS spend since the mark: ≈ 0.19.

## For the coordinator (review before tagging)

1. Re-run `uv run study run-manifest config/addendum_manifest.yaml --dry-run` and
   `shasum -a 256 config/addendum_manifest.yaml` (must equal prereg-v2a §6) right before the tag;
   any manifest edit means re-running `scripts/analysis/prereg_hashes.py` and updating §1/§6.
2. Ministral: the first CV pass had 1 parse-failure row; tune_router re-sent it (failures are not
   cached) and it succeeded, so the CV and the frozen map are from the error-free 79.5 pass; the
   `study run` file `p2a-dev-e6m_llm_ministral` still shows the ITT 78.8 with 1 error.
3. Guard gap: `turn_cost` treats E10c/E10t as free (the probe's Bedrock embeddings are not in
   `model_configs`). Real cost is a fraction of a cent; noted in prereg-v2a §6, not fixed.
4. `ManifestRun` has no `catalog_hash` field (prereg-v2 draft §6 says each entry carries it). The
   catalog hash is asserted by the analysis instead (prereg-v2a §1, §8). Add the field before
   Part B if the guard should check it.
5. For Part B "Bedrock embedder = whichever wins Part A dev CV": Titan (60.3) edges Cohere (59.6)
   within noise, and is ~4× faster and 6× cheaper.
6. T2.5 cap: `BUDGET__AWS_USD_CAP=54.11`, OpenRouter cap = ledger at launch + 0.2. Expected AWS ≈ 0.86.
