# Handoff: phase 2, tuning on dev-L (T5.1–T5.5)

Branch `feat/phase2-cloud-and-large-catalog`. Commits (no push): 3ec1bd4, 89bb6fb, 09c1d12,
92c7c84, 4486fab, ccc77a5, c32c9ef, 5d7ffc6, 17b0637, plus the docs/handoff commit. Every number
is on `data/dataset_dev_l.jsonl` (150 cases; sha `b02b3722…`) with the large catalog
**`bc7cd75fce87`** (recorded on every run). No test split was read. No local model was run.
Full log: `docs/tuning-effort-l.md` §B. Artifacts: `docs/results/phase2-dev-l/` (tuned blocks,
tune_router summaries, grid scripts, cascade reports).

## Tooling added (additive, phase-1 behaviour unchanged)

- `tune_router.py` / `fit_hybrid.py --split dev|dev_l` (dev_l = dev-L + in-process LARGE catalog);
  `calibrate_cascades.py` accepts a `dev_l` shadow.
- `scripts/analysis/apply_tuned_l.py <blocks.yaml>` writes tuned strategy blocks, per-config
  maps and thresholds into `config/experiments_l/*.yaml`. Blocks file:
  `docs/results/phase2-dev-l/tuned_blocks.yaml` (built by `docs/results/phase2-dev-l/scripts/make_blocks.py extra_hybrid.yaml`
  from the summaries; a map is kept only when cross-fitted ECE < raw ECE).
- **Rescore fix (09c1d12):** `rescore_file` scored large-split rows against the 18-tool
  `tools_list.json`; dev_l/test_l now default to `tools_list_large.json` (test added).
- Manifests: `config/freeze_dev_l_manifest.yaml` (dev-L shadow, Sonnet 1 rep, OQ-1),
  `config/dev_l_e2e_manifest.yaml` + `config/manifest/dev_l_e2e_validation_40.ids`.

## Results (dev-L, 5-fold CV seed 0; nested = estimate of the tuning procedure)

| strategy | nested joint [95% CI] | ECE skill raw→cal / tool raw→cal (map written?) | p50 ms (tuning, not benchmark) | US$/1k cases |
|---|---|---|---|---|
| E1 regex (after the dev-L round; optimistic) | 82.7 [76.7, 88.7] (before: 54.7) | 0.110→0.058 ✓ / 0.214→0.082 ✓ | 1 | 0 |
| E2 BM25 | 52.7 [44.7, 60.7] | 0.511→0.065 ✓ / 0.346→0.106 ✓ | 19 | 0 |
| E3 embedding (Titan v2) | 61.3 [53.3, 69.3] | 0.083 ✗ / 0.186→0.133 ✓ | 161 | ≈0.003 |
| E10 probe (Titan v2) | 66.0 [58.0, 73.3] | 0.060 ✗ / 0.115→0.085 ✓ | 176 | ≈0.003 |
| E11 hybrid (convex regex+classifier α 0.5) | 81.3 [75.3, 87.3] | 0.112→0.040 ✓ / 0.116→0.042 ✓ | ~180 | ≈0.003 |
| E6 Haiku 4.5 P0 | 84.0 [78.0, 89.3] | 0.065→0.038 ✓ / 0.070 ✗ | 3651 | 7.18 |
| E6m Ministral P0 | 78.7 [72.0, 84.7] (2 ITT errors) | 0.145→0.076 ✓ / 0.148→0.059 ✓ | 841 | 0.70 |
| E6n Nemotron P0 | 73.3 [66.0, 80.0] | 0.156→0.101 ✓ / 0.199→0.022 ✓ | 1397 | 0.33 |
| E4 Jev P0 | 86.7 [80.7, 92.0] (1 error) | 0.057→0.029 ✓ / 0.023 ✗ | 3620 | 1.28 |
| Sonnet 5 P0 (shadow only) | 84.0 [78.0, 89.3] | 0.123→0.022 ✓ / 0.047→0.037 ✓ | 5840 | 7.52 |
| E7-L regex → Jev | 86.0 [80.0, 91.3] (CV) | – | – | 1.04 routing |
| E9-L regex → Jev → Sonnet | 86.0 [80.0, 91.3] (CV) | – | – | 1.06 routing |
| E12-L hybrid → Jev → Sonnet | 82.7 [76.0, 88.7] (CV) | – | – | 1.07 routing |

- Parse failures all < 2% → no format-only fix. Haiku: 0 cache reads (P0 ~2.7k tokens < 4,096
  minimum), answers X3 for dev-L.
- Embedder decision: **Titan v2** (Part A recommendation; recorded in configs, tests, docs).
- BM25 grid 2 best: utterance/topk_sum k4, char 2–5, folding, shots, no quotes, okapi k1 1.2 b 0.75, history 2.
- Probe: C 1000, shots, description, history 2. Embedding: centroid k3 T 0.02 history 1 shots.

## Cascade thresholds (rule (a), budget 0.5 × Sonnet P0 dev-L = US$ 0.003761/case)

- E7-L regex 0.88; E8-L infeasible → fallback unconstrained (a) regex 0.88; **E9-L regex 0.88,
  Jev 0.76 / tool Jev 0.50** (= phase 1); E12-L hybrid 0.78, Jev 0.76 / tool Jev 0.50.
- Skill-stage coverage on dev-L: E9-L regex 70% (105/150), Jev 30%, Sonnet 0%; E12-L hybrid 79%.

## e2e validation (40 fixed dev-L ids, Sonnet executor, both COMPLETE, 0 errors)

| arm | legacy | sym | US$/turn billed |
|---|---|---|---|
| E0-L | 60.0 [45.0, 75.0] | 65.0 [50.0, 80.0] | 0.0139 |
| E9-L | 57.5 [42.5, 72.5] | 60.0 [45.0, 75.0] | 0.0165 |

Sym scorer: every row scored (no `None`), 0 unknown tools. Refreshed test-L estimates: B13 ≈ 4.2,
B14 ≈ 5.0, B15 ≈ 5.0, B16 ≈ 1.8 (US$; plan had 3.39 / 2.69 / 2.80 / 1.22) → re-run the
estimates at T6.1; the AWS 29.0 cap needs checking against these.

## Spend (this work)

AWS ledger 54.3209 → 58.0241 (**+3.70**, cap +6.00); OpenRouter 5.9191 → 6.1273 (**+0.21**,
cap +0.35). Main items: Haiku 1.08, Sonnet router 1.13, E0-L e2e 0.55, E9-L e2e 0.66, 8B 0.15,
Jev 0.19 (OR).

## Caveats / next

- The regex CV is optimistic (rules written while reading dev-L errors; ~0.5 h of the 4 h + 2 h
  timebox used). E9-L/E7-L thresholds rest on it.
- The host slept for hours on low battery during the grids; runs resumed by (case, rep); the
  hung E9-L e2e case was killed and resumed; no infra-error rows remain in any dev-L result.
- `docs/tuning-effort-l.md` p50/p95 are tuning latencies (concurrency 2–4), not benchmark.
- Next: T4.3 test-L generation (configs are freeze candidates now), then T6.1 freeze
  (`config/study_manifest_l.yaml` entries with `catalog_hash: bc7cd75fce87`).
