# Pre-registration prereg-v2: large catalog (Part B), split test-L, 62-tool catalog

Status: **FROZEN** at the git tag `prereg-v2`, before the first test-L row. Nothing below (configs,
thresholds, calibration maps, prompts, catalog, scorers, manifest, case-id files, analysis code)
changes after that row (§8). Part A (cloud addendum on the 18-tool catalog) is frozen separately in
`docs/prereg/prereg-v2a.md` (tag `prereg-v2a`). Source draft: `docs/prereg/prereg-v2-draft.md`.
Plan: `.omc/plans/autopilot-impl.md` T6.1. Dev-L tuning record: `docs/tuning-effort-l.md` §B,
`.omc/handoffs/p2-tuning.md`.

> T4.3 is complete (commit e1e8683). Every test-L value below was filled on 2026-10-02 before the
> tag and before any test-L row: the dataset sha, the case-id files and the test-L dry-run.

## 0. Inherited from prereg-v1 unchanged

Unit = case, reps averaged per case; ITT (an infra or parse failure is wrong); multi-label (any
acceptable label, first-label as sensitivity); out of scope = escalation counts as abstention; paired
cluster (case) bootstrap, 10,000 resamples, seed 20260930; NI = lower bound of the two-sided 95% CI
plus a one-sided sign-flip p-value with the shift; equivalence = TOST (90% CI inside the bounds);
two-sided = CI plus sign-flip p-value; Holm within each family; response cache per (case, rep,
rendered prompt); latency **only** from the dedicated benchmark; cost in three regimes; operations,
retry and abort rules of prereg-v1 §7.

**Phase-2 constraints (2026-10-02, binding):**
- no local model is run (no Ollama: no Qwen3-8B, no local qwen3-embedding). Regex and BM25 are CPU
  code, not models, and stay;
- OpenRouter is used only for `typesafe/jev-router`; everything else runs on Bedrock;
- Sonnet 5 is never a standalone router on test-L. It appears only as the last step of the E9-L /
  E12-L cascades and as the e2e executor.

## 1. Frozen artifacts

| artifact | value |
|---|---|
| code | the commit tagged `prereg-v2` |
| catalog | large profile (`CATALOG_PROFILE=large`, mcp-server-large on :8766), `catalog_hash` **bc7cd75fce87** (62 tools, 10 skills + globals; checked live at the freeze, 2026-10-02); `mcp_server/tools_list_large.json` sha256 `a0583726a351a862494c0f655b409c592e48c9a2f1c31ef43371b7ff63a88f07`. X2 small profile: `catalog_hash` **128584617807** (unchanged since phase 1), `tools_list.json` `a9776477226c398702032f7fdd05223fc0a013dfc68ebe0e8f749567e27aa123` |
| dev data | `data/dataset_dev_l.jsonl` sha256 `b02b3722f5c4e434dd97a4c6a4811ac18a1fd1945784a6375639acd0b376e238` (150 cases) |
| test data | `data/dataset_test_l.jsonl` (300 cases, generator seed 20261009, audited, automated adjudication; commit e1e8683). **TEST-L DATASET SHA: `ae21a5dbce16eb90278612f7dbcf875cb6610b7b12a49cb6f7f57e503d680ff2`** |
| routing scorer | legacy `scorer_hash` **e0eef1fb0073** (unchanged; routing primary, e2e sensitivity) |
| e2e scorer | symmetric `scorer_sym_hash` **5ad0f65296e4** (`src/routing_study/eval/scorers_sym.py`; e2e primary) |
| prompt | `prompt_hash` **c61ad0a7b7f8** (P0; no template change, no prompt search) |
| manifest | `config/study_manifest_l.yaml`, sha256 `788fac3665ba82e06703a644f42e753f1413441dcc8d3395071d6d8ce8bc2e6b` (73 entries) |
| latency ids | `config/manifest/latency_test_l_b{1..4}.ids` (4 × 25 stratified test-L cases, `scripts/analysis/latency_ids.py --split test_l`). sha256 b1 `0d616311ff839cc822afa844a7c3dc59bdbe9c75618b41ec26d16b4194371dd5`, b2 `ded21cf01feb9d1246a3f7dc919e5e1ed6eb937cdfe2c14e6fe9241b7c6dce09`, b3 `2550bd1ec7443ed6d9cc1dbca393c6600a54a2ad804bb20c61159ec8c9a5ab86`, b4 `70723d6305a5b77a42e2267902fded0c5a8d9a14c4d68a77ac47cb64877465a4` |
| X2 ids | `config/manifest/x2_test_l_orig.ids` (the orig subset, `scripts/analysis/x2_orig_ids.py`; n ≥ 60 asserted). **n = 114** of 300 (≥ 60 holds), sha256 `42cba58577b41b0ebb379f3fe5867610ea8560e7276eb11a05d2546a4a952945` |
| thresholds / calibration | written in `config/experiments_l/*.yaml` (§5); unchanged after the dev-L tuning commits (17b0637 and earlier) |
| analysis code | `scripts/analysis/phase2_b.py`, written before test-L at commit **27cacee**. At the tag, the only diff from 27cacee is the `TBD@freeze` constant block (catalog/scorer confirmations, `MANIFEST_L_SHA`, `DEV_FIXED_L`, `S7_PROBE`, `S2_MIN_N`, and `DATASET_SHA["test_l"]`). Check: `git diff 27cacee prereg-v2 -- scripts/analysis/phase2_b.py` |
| phase-1 hash lock | `tests/test_phase1_hashes.py` green at the tag |

### Per-run config hashes (asserted by the manifest version guard)

Every large-profile entry also asserts `catalog_hash bc7cd75fce87`; every X2 entry asserts
`128584617807`. `prompt_hash` is `c61ad0a7b7f8` for all. The `l-*` names are the ones pinned in
`phase2_b.py`.

| run(s) | config | config_hash |
|---|---|---|
| `l-e1-regex-routing-r1`, `l-e1-regex-routing-repeat20` | `experiments_l/e1_regex_l.yaml` | 9edc10d85a4e |
| `l-e2-bm25-routing-r1` | `experiments_l/e2_bm25_l.yaml` | 047a16011d05 |
| `l-e3-embedding-routing-r1` | `experiments_l/e3_embedding_l.yaml` | 3cd09a609c93 |
| `l-e10-classifier-routing-r1` | `experiments_l/e10_classifier_l.yaml` | 61260135d35a |
| `l-e11-hybrid-routing-r1` | `experiments_l/e11_hybrid_l.yaml` | 0078bcc597f8 |
| `l-shadow-tuned-routing-r3` (shadow set without Sonnet) | `experiments_l/e9_regex_jev_llm_l.yaml` + override | ae7dda1ab390 |
| `l-e4-jev-canonical-routing-r3` | `experiments_l/e4_jev_l.yaml` | d8d2f8940050 |
| `l-e6-haiku-canonical-routing-r1`, `-rep2-60` | `experiments_l/e6_llm_haiku_l.yaml` | 8b7b8fb00143 |
| `l-e6m-ministral-canonical-routing-r1`, `-repeat50` | `experiments_l/e6m_llm_ministral_l.yaml` | 1ce8c6004c5f |
| `l-e6n-nemotron-canonical-routing-r1`, `-repeat50` | `experiments_l/e6n_llm_nemotron_l.yaml` | ae768b0a8656 |
| `l-e9-tuned-routing-r3`, `l-e9-tuned-e2e-r1`, `l-e9-tuned-e2e-rep2-60` | `experiments_l/e9_regex_jev_llm_l.yaml` | 8236c879738c |
| `l-e7-tuned-routing-r3` | `experiments_l/e7_regex_jev_l.yaml` | babfafa1bdae |
| `x-l-e12-hybrid-tuned-routing-r3` | `experiments_l/e12_hybrid_jev_llm_l.yaml` | fd13e06c82a4 |
| `l-e0-native-e2e-r1`, `l-e0-native-e2e-rep2-60` | `experiments_l/e0_native_l.yaml` | 93c7c3ea1e02 (¹) |
| `l-e9-fullskill-e2e-r1` | E9-L + `routing.tool.expose_top_k: 6` | 2741f7281d8b |
| `lat-l-{regex,bm25,embedding,classifier,hybrid}-b1..4` | E1/E2/E3/E10/E11-L + latency overrides | d341905fd5ca / 09e347ca67bb / b57d9830966f / 8158869c2b7d / 31b1ccbfcf66 |
| `lat-l-{jev,haiku,e6m,e6n}-b1..4` | E4/E6/E6m/E6n-L + latency overrides | bf67bc0d09bf / 170370d07bed / 127123dc6afa / 5afc47143514 |
| `lat-l-{e7,e9}-b1..4` | E7-L / E9-L + latency overrides | 86b20f674287 / 987a841f839f |
| `l-x2-small-{e1,e2,e3,e10}-routing-r1` | `experiments/e1_regex`, `e2_bm25`, `e3_embedding_titan`, `e10_classifier_titan` | 2da827d0effb / 7bb5a5960490 / 73f81417a487 / 70374caa4b59 |
| `l-x2-small-{e4,e6m,e6}-routing-r1` | `experiments/e4_jev`, `e6m_llm_ministral`, `e6_llm_haiku` | acd7ff96155b / 0d8fbee553f3 / f6c0edce210b |

(¹) `mcp_url` is not part of `config_hash`, so E0-L has the same `config_hash` as phase-1 E0. The two
are told apart by `catalog_hash` (asserted on the entry and on every row) and by the run name.

Note on the dev-L e2e validation (T5.5): it ran with E9-L `config_hash` f8c5522232cc. The frozen
8236c879738c differs only in the BM25 and hybrid blocks and their maps (commits c32c9ef and
5d7ffc6). E9-L's cascade (regex 0.88 → Jev 0.76 → Sonnet; tool stage Jev 0.50 → Sonnet) does not
use those blocks, and its thresholds and maps are identical.

## 2. Arms (large catalog, test-L, ~300 cases)

- **Free routers (1 rep):**
  - E1 regex (agent-written rules, `config/regex_rules_l.yaml`);
  - E2 BM25;
  - E3 dense embedding on Bedrock Titan v2 (`amazon.titan-embed-text-v2:0`);
  - E10 linear probe on the Titan v2 vectors;
  - E11 hybrid (convex regex + probe, α 0.5).

  Titan v2 is the large-profile embedder (Part-A dev recommendation; `tuning-effort-l.md` §B). E3c
  (Cohere), E3t (≡ E3 here) and E10c are therefore **not** separate test-L runs, and `phase2_b.py`
  reports them as NOT RUN.
- **LLM / meta-routers (P0, canonical track):**
  - E4 Jev (`typesafe/jev-router`, OpenRouter), 3 reps;
  - E6 Haiku 4.5, 1 rep + rep 2 on 60 cases;
  - E6m Ministral 3 8B and E6n Nemotron Nano 9B v2 (reasoning off), on Bedrock, 1 rep + rep 2 on
    50 cases each.
- **Cascades (tuned track = P0; thresholds from the dev-L shadow, rule (a)), 3 reps each:**
  - E7-L: regex → Jev;
  - E9-L: regex → Jev → Sonnet 5;
  - E12-L: hybrid → Jev → Sonnet 5 (exploratory).
- **e2e (Sonnet 5 executor), 1 rep:**
  - E0-L: native, no router;
  - E9-L;
  - E9-L-fullskill: E9-L with every tool of the routed skill exposed (`expose_top_k` 6; large
    skills have 5–6 tools).
- **Not run (constraint):** E6b Qwen3-8B, local E3 qwen3-embedding, local E10 probe, and any
  standalone Sonnet router.

## 3. Hypotheses

Joint = joint top-1 routing accuracy (legacy routing scorer), ITT. `e2e_success_sym` = the
symmetric e2e scorer (§4). Paired by case. α = 0.05.

### Primary (confirmatory; Holm across H1-L, H2-L, H3-L)

- **H1-L ("is a router worth it?").** e2e_success_sym(E9-L) − e2e_success_sym(E0-L), two-sided,
  paired, 95% CI. A directional claim is made only if the CI excludes 0.
  - Expected MDE on n ≈ 300: about 5.5–7.5 pp.
  - Effect-size prior, written here and not part of the test: the phase-1 symmetric re-score gave
    E9 − E0 = −3.2 [−6.0, −0.3] pp (EXPLORATORY, `docs/results/phase1-sym/`). On the dev-L
    validation (40 cases), E9-L had 60.0 sym and E0-L 65.0.
  - Co-primary estimate: the per-turn cost ratio E9-L / E0-L (observed regime) with a CI.
- **H2-L (managed small LLM vs premium small LLM; re-specified by the 2026-10-02 constraint).**
  Joint(E6m Ministral 3 8B) − Joint(E6 Haiku 4.5) > −3 pp (NI). This replaces the draft's
  Ministral-vs-local-Qwen contrast, since no local arm runs on test-L.
  - Co-primary estimate: the p95 latency ratio E6m / E6 from the benchmark.
- **H3-L (cheap meta-router vs premium small LLM).** Joint(E4 Jev) − Joint(E6 Haiku 4.5) > −3 pp (NI).
  E4 is averaged over 3 reps per case.

A primary whose run is missing or not COMPLETE is reported as NOT RUN, never imputed. It enters
Holm with p = 1, so the family size stays 3.

Dev-L expectation (not part of the tests; nested or dev-L CV): E9-L 86.0, E7-L 86.0, E4 86.7,
E6 84.0, E6m 78.7, E6n 73.3.

### Secondary

- **Family S-e2e** (Holm within):
  - **S1.** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, one-sided. This confirms
    phase-1 D-002 on a fresh split.
  - **S2.** The same contrast as H1-L, restricted to the cases where both arms executed the same
    business calls. Equivalence ±3 pp (TOST).
    - OQ-2 is resolved: if that subset has fewer than 60 cases, S2 becomes estimation only (90% CI
      reported) and enters Holm with p = 1.
- **Family S-routing** (Holm within S4, S7):
  - **S3** (magnitude with a CI, not tested in Holm). Joint(E1 regex, test-L) − the fixed dev-L
    CV joint **82.7%** (after the dev-L round, optimistic; `tuning-effort-l.md` §B).
  - **S4.** Joint(E3 Titan embedding) − Joint(E1 regex), two-sided.
  - **S7.** Joint(E10 probe) − Joint(E4 Jev), two-sided. E10 (Titan) is the only large-profile probe,
    so it is the "best pre-declared probe".
  - **Dropped** under the constraint, out of the family: S5 (Cohere vs local embedding) and S6
    (Nemotron vs local Qwen3-8B). Their reference arms are local.

### Sensitivity (reported, not tested)

- H1-L under the legacy asymmetric scorer, side by side, with the count of cases where the verdict
  differs.
- First-label joint.
- The error-free intersection.
- ambiguo reported apart.
- Human-flagged cases excluded.

### Estimation only (CIs, no tests)

Per strategy:
- skill %, conditional tool %, recall@1/2/3;
- error and parse-failure rates (ITT); rep-flip rates (Haiku 60, 8B 50, regex 20);
- ECE and Brier (raw and dev-L calibrated);
- cost per 1k in three regimes;
- latency p50/p95 with the cold first case apart (`lat-l-*`, managed and CPU only);
- cascade coverage per step, including **regex coverage at its 0.88 threshold**;
- abstention precision and recall;
- the e2e decomposition, `args_invented`, `entity_grounded`, and executor variance (E0-L and E9-L
  on 60 cases);
- per category, per skill (original vs new), and per confusable group G1–G12.

E6n (Nemotron), E2, E11, E7-L and E12-L (exploratory) are estimation arms.

### Exploratory: catalog size, 18 vs 62 tools

- **X1 (cross-dataset, unpaired).** Joint(test-L) − Joint(test-v2) for each strategy present in
  both phases (phase-1 or Part-A test-v2 rows), with independent bootstraps per split. The same
  comparison is made for E0/E9 e2e under the sym scorer. The caveat in `phase2_b.py` `CAVEAT_X` is
  printed wherever X1 is shown.
- **X2 (paired catalog-size subset, secondary estimation).** The orig subset is every test-L case
  whose acceptable tools all lie in the 18 original tools, or that is out of scope.
  - It is routed by the small-profile frozen configs (E1, E2, E3 = Titan `e3_embedding_titan`,
    E10 = `e10_classifier_titan`, E4 Jev, E6m, E6 Haiku). The large-profile run restricted to the
    same cases is the comparison. The result is a paired Δ joint with a CI per strategy.
  - E11 is not run in X2: the phase-1 small hybrid uses the local probe.
- **X3.** Haiku cache behaviour (dev-L: P0 ≈ 2.7k tokens < the 4,096 cache minimum, 0 cache reads).
- **X4.** Phase-1 sym re-score (already reported as exploratory).

## 4. Metrics and scorers

- **Routing primary:** joint top-1 accuracy, legacy routing scorer `e0eef1fb0073`.
- **e2e primary:** `e2e_success_sym` (`scorers_sym.py`, `5ad0f65296e4`). The skill is attributed
  from behaviour, identically in both arms:
  1. the skill of the first business tool executed;
  2. otherwise, the skill of the tool credited by a clarification (inferred from the question);
  3. otherwise, escalation-only or host abstention → `__abstain__`;
  4. only global calls → `__global__`;
  5. no action → `__abstain__`.

  Success = the attributed skill is acceptable **and** (the first call is OK with valid args and
  finished, **or** a clarification is credited, **or** a later call recovers). The scorer never reads
  `native`, the router's skill or tool, or `resolved_by` (unit-tested).
- **e2e sensitivity:** legacy `e2e_success`.
- Both scorers are applied to the same raw bytes. `phase2_b.py` checks this.

## 5. Tuning, thresholds and calibration (dev-L only, frozen in `config/experiments_l/`)

All tuning used dev-L (150 cases): 5-fold CV stratified by category, seed 0, nested estimates.
test-L was generated after the configs were final (T4.3 after T5.5) and was not read.

| arm | frozen choice | dev-L joint [95% CI] | maps written (skill / tool) |
|---|---|---|---|
| E1 regex | 298 rules (~0.5 h of the 4 h + 2 h timebox), history 2 | 82.7 [76.7, 88.7] (optimistic) | Platt / Platt |
| E2 BM25 | utterance, topk_sum k 4, char 2–5, folding, shots, okapi k1 1.2 b 0.75, history 2 | 52.7 [44.7, 60.7] | ✓ / ✓ |
| E3 Titan | centroid, k 3, T 0.02, history 1, shots | 61.3 [53.3, 69.3] | – / ✓ |
| E10 Titan probe | C 1000, shots, description, history 2 | 66.0 [58.0, 73.3] | – / ✓ |
| E11 hybrid | convex regex + classifier, α 0.5 | 81.3 [75.3, 87.3] | ✓ / ✓ |
| E4 Jev | P0 | 86.7 [80.7, 92.0] | ✓ / – |
| E6 Haiku 4.5 | P0 | 84.0 [78.0, 89.3] | ✓ / – |
| E6m Ministral | P0, T 0 | 78.7 [72.0, 84.7] | ✓ / ✓ |
| E6n Nemotron | P0, T 0, `/no_think` | 73.3 [66.0, 80.0] | ✓ / ✓ |

- **Cascade thresholds.** Rule (a) of prereg-v1 §4: the maximum joint subject to a routing cost of
  at most 0.5 × the Sonnet P0 dev-L cost (budget US$ 0.003761 per case). Grid 0.50..0.99, step
  0.01. Fitted on the dev-L shadow, which included Sonnet at 1 rep on dev-L only (OQ-1), and
  cross-fitted. Results:
  - **E7-L:** regex 0.88.
  - **E9-L:** regex 0.88, Jev 0.76; tool stage Jev 0.50 (the same values as phase 1).
  - **E12-L:** hybrid 0.78, Jev 0.76; tool stage Jev 0.50.
  - Cross-fitted dev-L joint: E7-L 86.0, E9-L 86.0, E12-L 82.7.
  - Dev-L skill-stage coverage of E9-L: regex 70%, Jev 30%, Sonnet 0%.
- **Prompt.** P0 everywhere and no prompt search. Every dev-L parse-failure rate was below 2%, so no
  format-only fix was used.
- **Calibration.** A map is kept only where the cross-fitted ECE is below raw.

## 6. Run plan, order and budget

Manifest `config/study_manifest_l.yaml` (sha256 in §1): 73 entries on `split: test_l`. The priority
order follows the plan's drop order (`autopilot-impl.md` §5). The guard refuses runs and never
reorders them, so the lowest priorities are the first ones a cap removes: executor variance (B16),
then E9-L-fullskill (B15), then X2-Haiku (B18), then latency (B17).

| priority | runs | cases × reps |
|---|---|---|
| 10 | E1, E2, E3, E10, E11 | 300 × 1 |
| 11 | E1 repeat (determinism) | 20 × 2 |
| 20 | shadow, E9-L decider, set {regex, bm25, embedding, classifier, hybrid, jev}, no Sonnet in the set | 300 × 3 |
| 25 | E4 Jev | 300 × 3 (cache hits of the shadow's Jev samples) |
| 25 | E6 Haiku, E6m, E6n | 300 × 1 |
| 30 | E9-L, E7-L routing | 300 × 3 |
| 31 | E12-L routing (exploratory) | 300 × 3 |
| 40 | **E0-L e2e, E9-L e2e (H1-L)** | 300 × 1 |
| 50 | Haiku rep 2; E6m, E6n rep 2 (rep 1 = cache hit) | 60 × 2; 50 × 2 |
| 70 | `lat-l-*` blocks 1–4 × {regex, bm25, embedding, classifier, hybrid, jev, haiku, e6m, e6n, e7, e9}, interleaved by block, concurrency 1, caches off, fresh `.cache/latency-l` | 4 × 25 per arm |
| 80 | X2 small profile: E1, E2, E3 (Titan), E10 (Titan), E4, E6m | orig subset (114) × 1 |
| 81 | X2 small profile: E6 Haiku | orig subset × 1 |
| 85 | E9-L-fullskill e2e (S1) | 300 × 1 |
| 90 | executor variance E0-L, E9-L | 60 × 1 |

Moving S1 from the draft's priority 45 to 85 follows the plan's drop order, which drops B15 before
B18-Haiku and the latency blocks.

**Dry-run.**
- On a **dev-L stand-in** (2026-10-02; the same manifest with `split: dev_l` and dev-L id files), all
  73 entries were PLAN with 0 ABORT: every `config_hash`, `prompt_hash` and `catalog_hash`
  (large and small) reproduces.
- The **test-L dry-run** is re-run after T4.3: `uv run study run-manifest config/study_manifest_l.yaml --dry-run`.
  **Result (2026-10-02, after e1e8683): 73 / 73 entries PLAN, 0 ABORT, 0 keys present (0 rows on
  disk).** Every `config_hash`, `prompt_hash` and `catalog_hash` reproduces on test-L, and every id
  file resolves inside the split. `prereg_hashes.py` was re-run and left the manifest unchanged.

### Budget

- **Marks:** phase-2 ledger mark AWS 52.11 / OpenRouter 5.83 (`docs/prereg/phase2-budget.md`).
- **Caps** (the 2026-10-02 constraint update replaces the plan's T6.2 formula):
  - AWS phase-2 total ≤ US$ 40, so the AWS ledger ceiling is **92.11**
    (`BUDGET__AWS_USD_CAP=92.11`);
  - the OpenRouter ceiling is **9.43** = 5.83 + 3.6 (`BUDGET__OPENROUTER_USD_CAP=9.43`).
- **Ledger at the freeze** (after T4.3): AWS 59.71 / OR 6.13. That leaves **32.40 AWS** and
  **3.30 OR** for this manifest.

Expected cost per item. Each figure is a dev-L per-case cost measured in T5.3–T5.5 multiplied by the
test-L size (300 cases; X2 = 114, the orig subset):
- Haiku 7.18, Ministral 0.70, Nemotron 0.33 and Jev 1.28 US$ per 1k cases;
- E9-L routing 1.03 per 1k (Jev tool stage 0.95, Sonnet fallback ≈ 0.11);
- e2e per case: E0-L 0.0139 and E9-L 0.0165;
- small profile: Haiku 4.97, Ministral 0.45 and Jev 0.78 per 1k.

| priority / item | AWS US$ | OR US$ |
|---|---|---|
| 10 free routers + shadow Titan vectors | 0.01 | – |
| 20/25 shadow r3 + E4 Jev r3 (shared Jev samples; +30% tool-stage misses of the E9 decider) | 0.10 | 1.41 |
| 25 E6 Haiku r1 (B10) | 2.15 | – |
| 25 E6m + E6n r1 (B11) | 0.31 | – |
| 30/31 E9-L, E7-L, E12-L r3 (Jev mostly cache hits; Sonnet fallback) (B12) | 0.10 | 0.17 |
| 40 **E0-L e2e** (B13) | 4.16 | – |
| 40 **E9-L e2e** (B14) | 4.94 | – |
| 50 Haiku rep2-60 + 8B rep2-50 | 0.48 | – |
| 70 latency, 11 arms × 100, caches off (B17) | 0.83 | 0.33 |
| 80/81 X2 on the 114 orig cases (B18) | 0.62 | 0.09 |
| 85 E9-L-fullskill e2e (B15; +5% for the larger tool exposure) | 5.18 | – |
| 90 executor variance on 60 (B16) | 1.82 | – |
| **expected total** | **20.71** | **2.00** |
| with 25% contingency | 25.88 | 2.50 |
| available under the caps (ledger at the freeze) | 32.40 | 3.30 |

- **OR worst case.** If no Jev tool-stage prompt of the E9-L / E7-L / E12-L deciders were a cache
  hit, OR would reach about 3.3, which equals the OR headroom. The latency and X2 Jev entries would
  then be the ones refused.
- **The guard's a-priori prices are not an upper bound for two items:**
  - Jev has no list price, so the guard's a-priori price for it is 0;
  - Haiku's a-priori price (2.6 per 1k) is below the measured 7.18 per 1k.

  The per-call ledger caps above therefore enforce these two accounts. A run stopped by
  `BudgetExceededError` is a deviation, reported as not run (§8).

## 7. Stopping and deviation rules

- No change to configs, prompts, labels, thresholds, calibration maps, catalog, scorers, the manifest,
  the id files or `phase2_b.py` after the first test-L row.
- Infra errors: up to 2 retries of the error rows. A run with more than 2% errors is FLAGGED and
  redone from scratch, never patched.
- **Budget stop.** If the AWS phase-2 delta reaches US$ 38 (ledger 90.11), or OR reaches 9.43,
  before every priority-≤ 40 run is COMPLETE: stop and log a deviation. The primaries are reported
  with whatever is COMPLETE. An incomplete primary is reported as not run, never imputed. The
  delta must never exceed AWS 40.
- **Data stop** (before the tag, so not a deviation): if the test-L audit flags more than 40% of
  cases, or the orig subset is under 60 cases, stop and decide (logged) whether to regenerate or
  top up the affected slots.
- Label corrections after the run go into a separate rescore and never replace the analysis.
- Deviations are appended to `docs/prereg/deviations-v2.md` with a timestamp.

## 8. Analysis plan

`uv run python scripts/analysis/phase2_b.py --manifest config/study_manifest_l.yaml` writes
`docs/results/phase2-b/{primary,secondary,estimation,catalog_size}.{md,json}` and
`estudos/figuras/final-b-*.png`. It is idempotent, and the draft's `final_l_all.py` /
`docs/results/phase2/` are this script (naming only).

- **Provenance checks, which fail loudly.** On every row: catalog, scorer, prompt and dataset hashes,
  plus the split. Also checked:
  - one config hash per file, equal to the manifest's frozen value;
  - the legacy and sym files of an e2e run rescored from the same raw bytes;
  - the dataset, the scorer code, the tools snapshots and the manifest bytes against §1.
- **Run eligibility.** A run is analysed only when the manifest log says COMPLETE.
- **Output contents:**
  - H1-L under both scorers;
  - every number tagged [C], [E] or [X];
  - the X1/X2 caveats in every catalog-size table.
- **Write-up:** new pt-BR `estudos/` chapters plus the `docs/` mirror. Phase-1 chapters are not
  edited, apart from links.

## 9. Threats specific to Part B

- **Optimistic regex.** The rules were written while reading dev-L errors. The E9-L / E7-L
  thresholds rest on them, and test-L regex coverage at 0.88 is reported (S3).
- **One embedder.** Titan v2 was chosen on Part-A dev. Cohere has no test-L arm.
- **H2-L re-specified.** It now compares two managed models; the local 8B comparison exists only on
  test-v2 (Part A).
- **Jev drift** (plan R9). The served models are recorded per call.
- **Auditor/generator families** differ from phase 1 (Bedrock Kimi K2.5 generator; gpt-oss-120b and
  DeepSeek v3.2 auditors). Label quality is reported through κ.
- **X1 is not a size effect** (§3). X2 controls the cases but not the per-catalog tuning.
