# Pre-registration prereg-v2a: cloud addendum (Part A), split test-v2, 18-tool catalog

Status: **FROZEN** at the git tag `prereg-v2a`, before the first Part-A test-v2 row. Nothing below
(configs, calibration maps, prompts, manifest, scorers, catalog) changes after that row
(prereg-v2 §8). Part B (large catalog) is pre-registered separately (`prereg-v2-draft.md` → `prereg-v2.md`).
Plan: `.omc/plans/autopilot-impl.md` T2.4. Dev tuning record: `docs/tuning-effort-l.md` §A.

## 0. Inherited from prereg-v1 unchanged

Unit = case, reps averaged per case; ITT (an infra or parse failure is wrong); multi-label (any acceptable
label, first-label as sensitivity); out of scope = escalation counts as abstention; paired cluster (case)
bootstrap, 10,000 resamples, seed 20260930; NI = lower bound of the two-sided 95% CI plus a sign-flip
p-value with the shift; two-sided = CI plus sign-flip p-value; Holm within the family; response cache per
(case, rep, rendered prompt); latency **only** from the dedicated benchmark; cost in three regimes;
operations, retry and abort rules of prereg-v1 §7.

**Phase-2 constraint (2026-10-01, binding):** no local model is run (no Ollama Qwen3-8B, no local
qwen3-embedding); OpenRouter only for `typesafe/jev-router`; everything else on Bedrock.

## 1. Frozen artifacts

| artifact | value |
|---|---|
| code | the commit tagged `prereg-v2a` |
| catalog | small profile, `catalog_hash` **128584617807** (unchanged since phase 1; asserted on every row by the analysis) |
| data | `data/dataset_test_v2.jsonl` sha256 `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66` (349 cases, unchanged); dev `data/dataset_dev.jsonl` `112fc7f0791e35cf1e250a40e362698212f029b4209b6ff7f33dc33717a8874a` |
| routing scorer | legacy `scorer_hash` **e0eef1fb0073** (unchanged). Part A is routing-only: the sym e2e scorer (`5ad0f65296e4`) is not used |
| prompt | `prompt_hash` **c61ad0a7b7f8** (P0; no template change, no prompt search) |
| manifest | `config/addendum_manifest.yaml`, sha256 recorded in §6 |
| latency ids | `config/manifest/latency_test_v2_b{1..4}.ids` (phase-1 files, 4 × 25 stratified cases), sha256 prefixes `ae81eacf2b492fc8`, `8fd97293c7683b86`, `48cdf829874e34eb`, `65b2efa0035d5d23` |
| thresholds / calibration | written in the six Part-A configs (§5); no cascade in Part A |
| phase-1 hash lock | every `config/study_manifest.yaml` / `study_manifest_explore.yaml` entry reproduces its frozen `config_hash` and `prompt_hash` at the tag (checked 2026-10-01: 104 entries, 0 mismatches) |

### Per-run config hashes (asserted by the manifest version guard)

| run(s) | config | config_hash |
|---|---|---|
| `v2a-e3c-cohere-routing-r1` | `config/experiments/e3_embedding_cohere.yaml` | 56f1708d24de |
| `v2a-e3t-titan-routing-r1` | `config/experiments/e3_embedding_titan.yaml` | 73f81417a487 |
| `v2a-e10c-cohere-routing-r1` | `config/experiments/e10_classifier_cohere.yaml` | fc05bbd1c5aa |
| `v2a-e10t-titan-routing-r1` | `config/experiments/e10_classifier_titan.yaml` | 70374caa4b59 |
| `v2a-e6m-ministral-canonical-routing-r1`, `-repeat50` | `config/experiments/e6m_llm_ministral.yaml` | 0d8fbee553f3 |
| `v2a-e6n-nemotron-canonical-routing-r1`, `-repeat50` | `config/experiments/e6n_llm_nemotron.yaml` | efb00ce5b9f8 |
| `lat-a-e3c-b{1..4}` / `lat-a-e3t-b*` / `lat-a-e10c-b*` / `lat-a-e10t-b*` | same configs + latency overrides | dc14a444fd4b / 310f335fdb80 / ab5f1d2d0d13 / 6377e34f786e |
| `lat-a-e6m-b*` / `lat-a-e6n-b*` | same configs + latency overrides | 67e47f9c08e8 / 435d2cee8b41 |
| `lat-a-jev-b*` / `lat-a-haiku-b*` (managed anchors) | `e4_jev.yaml` / `e6_llm_haiku.yaml` + latency overrides | 5cf75faa33f3 / 5535a7588de0 (= the phase-1 `lat-jev-b*` / `lat-haiku-b*` hashes: identical configs) |

### Re-used phase-1 rows (frozen, read-only; the local comparison arms)

| role | file (rescored) | sha256 prefix |
|---|---|---|
| A1/A2 reference, E6b Qwen3-8B local, P0 canonical | `results/rescored/v2-e6b-qwen-canonical-routing-r1.jsonl` (config_hash 903a4a1e56d3) | 6a99aab7fc6b116d |
| A3/A4 reference, E3 qwen3-embedding 8B local | `results/rescored/v2-e3-embedding-routing-r1.jsonl` (1899b6f414a5) | 4c13be42cda91614 |
| E10c/E10t estimation peer, local probe | `results/rescored/v2-e10-classifier-routing-r1.jsonl` (616af886b783) | b14c2893e454ce80 |
| local latency | `results/rescored/lat-qwen-b*`, `lat-embedding-b*`, `lat-classifier-b*` (phase-1 window) | – |
| drift of the managed anchors | `results/rescored/lat-jev-b*`, `lat-haiku-b*` (phase-1 window) | – |

## 2. Arms (catalog small, test-v2, 349 cases, routing-only)

New managed routers, all on Bedrock `sa-east-1` except where noted:
- **E3c**: dense-embedding router on Cohere Embed v4 (`global.cohere.embed-v4:0`, cross-region inference
  profile; queries `search_query`, documents `search_document`).
- **E3t**: dense-embedding router on Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024-d).
- **E10c / E10t**: linear probe (logistic regression on catalog utterances) on the Cohere / Titan vectors.
- **E6m**: Ministral 3 8B (`mistral.ministral-3-8b-instruct`), P0, temperature 0, forced named tool.
- **E6n**: Nemotron Nano 9B v2 (`nvidia.nemotron-nano-9b-v2`), P0, temperature 0, reasoning off (`/no_think`).

Comparison arms (not re-run): the phase-1 local rows of §1, paired on the same 349 cases. Phase-1
Haiku/Jev/Sonnet accuracy rows are context only.

## 3. Hypotheses

### Family A (secondary, confirmatory for the addendum; Holm across A1–A4; α = 0.05)

Joint = joint top-1 routing accuracy (legacy routing scorer), ITT, 1 rep per arm, paired by case.

- **A1 (NI, margin 3 pp).** Joint(E6m Ministral) − Joint(E6b Qwen3-8B local) > −3 pp.
- **A2 (NI, margin 3 pp).** Joint(E6n Nemotron) − Joint(E6b) > −3 pp.
- **A3 (two-sided).** Joint(E3c Cohere) − Joint(E3 local qwen3-embedding).
- **A4 (two-sided).** Joint(E3t Titan) − Joint(E3 local).

Dev expectation (not part of the test; `docs/tuning-effort-l.md` §A): E6m 79.5, E6n 78.1 vs E6b 82.2 (dev CV);
E3c 59.6, E3t 60.3 vs E3 77.5 (nested CV). A3/A4 are expected to be large negative differences.

### Estimation only (CIs, no tests)

- skill %, conditional tool %, recall@1/2/3 for every new arm; E10c/E10t vs the local probe E10 and vs
  their own embedding router (paired Δ with CI);
- error and parse-failure rates per arm (ITT); flip rate rep 1 vs rep 2 on the 50 stratified cases (E6m, E6n);
- ECE and Brier, raw and dev-calibrated;
- cost per 1k cases in the three regimes;
- **latency** p50/p95 with bootstrap CIs, cold first case of each run apart:
  - same window: the six new arms vs the managed anchors Jev and Haiku 4.5, re-run interleaved by block;
  - other window: the six new arms vs the phase-1 local blocks (`lat-qwen`, `lat-embedding`, `lat-classifier`).
    **Caveat (mandatory wherever shown):** different time window; same Mac (M5 Pro 48 GB) for the local side,
    Bedrock `sa-east-1` from that Mac for the managed side. Drift is estimated as Δ p50/p95 of the managed
    anchors between their phase-1 and Part-A blocks; it is reported, never subtracted.

**Decision rule for the enterprise matrix (descriptive).** A managed option "qualifies" at a latency budget
when its p95 upper CI is under the budget **and** its joint is not inferior (A1/A2 rule for the 8B models; for
the embedders, the A3/A4 CI excludes a loss larger than 3 pp) to its local peer.

## 4. Metrics and scorers

Routing primary: joint top-1 accuracy with the legacy scorer (`e0eef1fb0073`), unchanged. Secondary routing
metrics as in `docs/metrics.md`. No e2e run in Part A.

## 5. Tuning, thresholds and calibration (dev only, frozen in the configs)

All tuning used the phase-1 dev split (151 cases), 5-fold CV stratified by category, seed 0; test-v2 was not
read. Calibration maps (isotonic or Platt by CV Brier for the embedders; isotonic for the LLMs, the phase-1
LLM procedure) are written only where the cross-fitted ECE is lower than raw (decision 2026-10-01).

| arm | procedure | frozen choice | dev joint [95% CI] (nested) | maps written |
|---|---|---|---|---|
| E3c | phase-1 D1 324-point grid; T by calibrated Brier | topk_vote k 5, T 0.1, history 2, shots, no instruction | 59.6 [51.7, 67.5] | skill (Platt) + tool (isotonic) |
| E3t | same | centroid, T 0.02, history 1, shots, no instruction | 60.3 [52.3, 68.2] | skill (isotonic) + tool (Platt) |
| E10c | phase-1 D4 64-point probe grid + 8-point C × history refinement | C 10, shots, description, no instruction, history 0 | 53.6 [45.7, 61.6] / 56.3 [48.3, 64.2] | tool only (skill ECE not lower) |
| E10t | same | C 0.1, shots, description, no instruction, history 0 | 60.9 [53.0, 68.9] / 59.0 [51.0, 66.9] | skill + tool (isotonic) |
| E6m | P0 only (no prompt search) | P0, T 0 | 79.5 [72.8, 86.1] | skill + tool (isotonic) |
| E6n | P0 only | P0, T 0, `/no_think` | 78.1 [71.5, 84.8] | skill + tool (isotonic) |

The 8B dev parse-failure rates (Ministral 0.3% of calls, Nemotron 0.7%; error rows 0.7% → 0 and 1.3%) are under
2%: no format-only fix was used.

## 6. Run plan, order and budget

Manifest `config/addendum_manifest.yaml`, sha256 `177e374a8ee0f07303fc0244110c0ac5fa95f6b276d9006d30f2cdd54ac1149e`. Priority order:

| priority | runs | cases × reps |
|---|---|---|
| 10 | E3c, E3t, E10c, E10t | 349 × 1 |
| 20 | E6m, E6n (canonical P0) | 349 × 1 |
| 21 | E6m, E6n rep 2 on 50 stratified cases (rep 1 = cache hit of the r1 run) | 50 × 2 |
| 70 | `lat-a-*`: blocks 1–4 × {E3c, E3t, E10c, E10t, E6m, E6n, Jev, Haiku}, interleaved by block, concurrency 1, response caches off, fresh `cache_dir` `.cache/latency-a` | 4 × 25 per arm |

`study run-manifest config/addendum_manifest.yaml --dry-run` at the freeze: every entry PLANNED, no ABORT
(hashes and prompt tracks reproduce), 0 rows on disk.

**Budget.** Phase-2 mark AWS 52.11 / OpenRouter 5.83 (`docs/prereg/phase2-budget.md`). Part-A run cap (plan T2.5):
`BUDGET__AWS_USD_CAP` = **54.11** (mark + 2.0) and the OpenRouter cap = ledger at launch + **0.2**.
Expected (dev-measured per-case costs): 8B r1 + rep2 ≈ US$ 0.27; 8B latency ≈ 0.07; Haiku anchor ≈ 0.50; embeddings
(test + latency + indexes) ≈ 0.02; **AWS ≈ 0.86**; Jev anchor ≈ **OR 0.08**. The guard runs before every entry; a
refused entry is a deviation, reported as not run, never reordered. Drop order if a cap is hit: the anchors
(lowest priority) first. Note: the guard prices E10c/E10t as free (the probe's Bedrock query embeddings are not
counted a priori); their real cost is a fraction of a cent per run.

## 7. Stopping and deviation rules

As prereg-v2 §8: no change to configs, prompts, labels, calibration maps, catalog or scorers after the first
Part-A test-v2 row; up to 2 retries of the error rows; a run > 2% errors is FLAGGED and redone from scratch;
deviations appended with a timestamp to `docs/prereg/deviations-v2.md`.

## 8. Analysis plan

`scripts/analysis/addendum_all.py` → `docs/results/addendum/` (idempotent): family A with Holm; the estimation
tables of §3; cost per 1k in three regimes; latency p50/p95 (cold case apart) for the same-window comparison and
the cross-window local comparison with the drift line; the local-vs-managed matrix using the re-used phase-1
rows. Every row's `catalog_hash`, `config_hash` and `prompt_hash` is asserted against §1.

## 9. Threats specific to Part A

- **Re-use of test-v2** (plan R10). Analysts have read the phase-1 test-v2 errors. Mitigation: the Part-A arms
  were tuned on dev only, with the phase-1 grids verbatim and no hand rules, and frozen here before any new
  test-v2 row.
- **Local arms from another time window.** Accuracy is unaffected (deterministic local rows, same cases);
  latency is (see the §3 caveat).
- **Cohere is served through a cross-region inference profile** (`global.`): InvokeModel does not report the
  serving region, so its latency includes whatever cross-region routing Bedrock applied.
- **Jev drift** (plan R9): the served models may have changed since phase 1; the anchor is re-run, never re-used.
