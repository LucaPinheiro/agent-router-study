# Pre-registration prereg-v2 (DRAFT): cloud addendum (Part A) and large catalog (Part B)

Status: **DRAFT**. Not frozen. The frozen version will be `docs/prereg/prereg-v2.md`:
- Part A is frozen at the git tag `prereg-v2a` before the first new test-v2 row.
- Part B is frozen at the tag `prereg-v2` before the first test-L row.

Fields marked `TBD@freeze` are filled at freeze time (hashes, thresholds, calibration maps). No other field may
change after the tag. Plan: `.omc/plans/autopilot-impl.md`. Spec: `.omc/autopilot/spec.md`.

## 0. What is inherited from prereg-v1 unchanged

- Unit of analysis = case. Reps are averaged per case.
- ITT: an infra or parse failure counts as wrong.
- Multi-label: any acceptable label counts, with first-label as a sensitivity.
- Out of scope: escalation counts as abstention.
- Bootstrap: paired cluster (case) bootstrap, 10,000 resamples, seed 20260930.
- Tests:
  - non-inferiority (NI) uses the lower bound of the two-sided 95% CI plus a sign-flip p-value with a shift;
  - equivalence uses TOST, accepted when the 90% CI lies inside the bounds;
  - two-sided tests use the CI plus a sign-flip p-value;
  - Holm correction within each family.
- Response cache per (case, rep, rendered prompt).
- Latency comes **only** from the dedicated benchmark.
- Cost is reported in three regimes.
- Operations, retry and abort rules as in §7 of prereg-v1.

## 1. Frozen artifacts (TBD@freeze)

| Artifact | Part A | Part B |
|---|---|---|
| Code | commit at `prereg-v2a` | commit at `prereg-v2` |
| Catalog hash | small `128584617807` (unchanged) | large `TBD` (`CATALOG_PROFILE=large`) |
| Data | `dataset_test_v2.jsonl` (sha `6637c479…`, unchanged), dev `112fc7f0…` | `dataset_dev_l.jsonl` `TBD`, `dataset_test_l.jsonl` `TBD` (audited, automated adjudication) |
| Scorers | legacy `e0eef1fb0073` (routing; e2e sensitivity); sym `TBD` (`scorers_sym.py`) | same |
| Prompt hash | `c61ad0a7b7f8` (P0; no template change) | same |
| Manifest | `config/addendum_manifest.yaml` sha `TBD` | `config/study_manifest_l.yaml` sha `TBD` |
| Thresholds and calibration | written in the Part-A configs | written in `config/experiments_l/*` (E7-L, E9-L via rule (a)) |
| Phase-1 hash lock | `tests/test_phase1_hashes.py` green at the tag | green at the tag |

## 2. Arms

- **Part A (catalog small, test-v2, 349 cases).**
  - New routers: E3c (Cohere embed-v4 embedding router), E3t (Titan v2 embedding router), E10c and E10t (linear
    probes on those vectors), E6m (Ministral 3 8B), E6n (Nemotron Nano 9B v2, reasoning off).
  - Comparison arms reuse the frozen phase-1 rows on the same cases: E6b Qwen3-8B local, E3 qwen3-embedding 8B
    local, E10 local probe. Phase-1 Haiku and Jev are context only.
- **Part B (catalog large, test-L, ~300 cases).**
  - Routing: E1 regex, E2 BM25, E3 local embedding, E3c, E3t, E10 (local and Cohere), E11 hybrid, E4 Jev,
    E6 Haiku 4.5, E6b Qwen3-8B, E6m, E6n, E7-L (regex → Jev), E9-L (regex → Jev → Sonnet).
  - e2e: E0-L (native Sonnet 5), E9-L, E9-L-fullskill (E9-L with `expose_top_k` = all skill tools).
  - All LLM routers use **P0**. Sonnet 5 appears only as E9-L's last step and as the executor.

## 3. Hypotheses

### Part A: family A (secondary, confirmatory for the addendum; Holm across A1–A4; α = 0.05)

- **A1 (NI).** Joint(E6m Ministral) − Joint(E6b Qwen3-8B local) > −3 pp.
- **A2 (NI).** Joint(E6n Nemotron) − Joint(E6b) > −3 pp.
- **A3 (two-sided).** Joint(E3c Cohere) − Joint(E3 local qwen3-embedding).
- **A4 (two-sided).** Joint(E3t Titan) − Joint(E3 local).

Estimation only (no test): p50/p95 latency of each new strategy against the anchors re-run in the same window
(local Qwen, local embedding, Jev, Haiku); cost per 1k; E10c/E10t; flip rate (rep2 on 50 cases); parse-failure rate.

Decision rule for the enterprise matrix (descriptive): a managed option "qualifies" at a latency budget when its
p95 upper CI is under the budget **and** its joint is not inferior to the local peer.

### Part B: primary (confirmatory; Holm across H1–H3; α = 0.05)

- **H1-L ("is a router worth it?", e2e, symmetric scorer).** e2e_success_sym(E9-L) − e2e_success_sym(E0-L),
  two-sided, paired, with a 95% CI. A directional claim is made only if the CI excludes 0.
  - Expected MDE on n ≈ 300 is about 5.5–7.5 pp.
  - The phase-1 sym re-score (exploratory, `docs/results/phase1-sym/`) is the effect-size prior. It is written down
    at freeze and does not change the test.
  - Co-primary estimate: cost per turn ratio E9-L / E0-L, observed regime, with a CI.
- **H2-L (managed vs local 8B).** Joint(E6m Ministral) − Joint(E6b Qwen3-8B) > −3 pp (NI).
  - Co-primary estimate: the p95 latency ratio E6m / E6b, from the benchmark.
- **H3-L (cheap meta-router vs premium small LLM).** Joint(E4 Jev) − Joint(E6 Haiku 4.5) > −3 pp (NI).

### Part B: secondary

- **Family S-e2e** (Holm within):
  - **S1.** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, one-sided. This confirms phase-1
    exploratory finding D-002 on a fresh split.
  - **S2.** e2e_success_sym(E9-L) − e2e_success_sym(E0-L) restricted to the cases where both arms made the same
    business calls. If the attribution asymmetry is gone, this should be ≈ 0, so the test is equivalence
    ±3 pp (TOST).
- **Family S-routing** (Holm within):
  - **S3.** Regex test-L − dev-L CV joint < 0 (magnitude with a CI; dev fixed).
  - **S4.** Joint(E3 local) − Joint(E1 regex), two-sided.
  - **S5.** Joint(E3c Cohere) − Joint(E3 local), two-sided.
  - **S6.** Joint(E6n Nemotron) − Joint(E6b) > −3 pp (NI).
  - **S7.** Joint(E10 best pre-declared probe) − Joint(E4 Jev), two-sided. The "best pre-declared probe" is the
    probe with the higher dev-L nested CV joint, fixed at freeze.

**Sensitivity, not tested.**
- H1-L under the **legacy asymmetric scorer** (prereg-v1 `e2e_success`). Both numbers are reported side by side,
  together with the count of cases where the verdict differs.
- Also: first-label joint; the error-free intersection; ambiguo reported apart; the human-flagged cases excluded.

### Estimation only (CIs, no tests)

Per strategy:
- skill %, conditional tool %, recall@1/2/3;
- error and parse rates; rep-flip rates (Haiku 60, Qwen/8B 50);
- ECE and Brier (raw and dev-L-calibrated);
- cost per 1k (three regimes);
- latency p50/p95 (cold first case apart);
- cascade coverage per step, including **regex coverage at its threshold**;
- abstention precision and recall;
- the e2e decomposition, plus `args_invented`, `entity_grounded` and executor variance (E0-L and E9-L on 60 cases);
- per category, per skill (original vs new), per confusable group G1–G12.

### Exploratory: catalog size, 18 vs 62 tools

- **X1 (cross-dataset, unpaired).** For each strategy present in both phases, Joint(test-L) − Joint(test-v2), with
  **independent** bootstraps per split, and the same comparison for E0/E9 e2e (sym scorer on both).
  - **Caveat (mandatory wherever it is shown):** the datasets differ. They have different cases, different label
    sets and different catalog text. They share the generator, the category proportions and the dedupe procedure,
    but the case difficulty is not controlled. Routers are re-tuned per catalog, so Δ measures "system at 18 vs
    system at 62", not a pure size effect. Absolute accuracies are not production estimates.
- **X2 (paired catalog-size subset, secondary estimation).** The orig subset of test-L is every case whose
  acceptable tools all lie in the 18 original tools, or that is out of scope; n ≥ 60 is guaranteed by the quota.
  - It is routed by the small-profile routers (phase-1 configs, frozen) and by the large-profile routers on the
    **same cases**, giving a paired Δ joint with a CI per strategy: free routers, Jev, Ministral, Haiku.
  - This isolates the effect of adding 44 confusable tools on cases that the small catalog can answer.
  - Remaining caveat: each profile has its own tuning (dev vs dev-L).
- **X3.** Haiku cache behaviour with the larger prompt (does it cross the 4,096-token cache minimum?) and its
  effect on cost.
- **X4.** Phase-1 sym re-score (already run before freeze; reported as exploratory and never re-labelled).

## 4. Metrics and scorers

- **Routing primary:** joint top-1 accuracy (legacy routing scorer, unchanged).
- **e2e primary:** `e2e_success_sym` (`src/routing_study/eval/scorers_sym.py`). The skill is attributed from
  behaviour, identically in both arms:
  1. the skill of the first business tool the server executed;
  2. otherwise, the skill of the tool credited by a clarification, inferred from the question asked, never from
     the router's tool;
  3. otherwise, an escalation-only turn or a host abstention → `__abstain__`;
  4. only global calls → `__global__`;
  5. no action → `__abstain__`.

  Success = the attributed skill is acceptable **and** (the first call is OK with valid args and finished, **or**
  a clarification is credited, **or** a later call recovers). Its decomposition and `args_invented` are as in
  prereg-v1. The scorer never reads `native`, the router's skill or tool, or `resolved_by`. A unit test enforces this.
- **e2e sensitivity:** legacy `e2e_success`.

## 5. Tuning and thresholds (all on dev / dev-L; frozen at the tag)

- **Prompt.** P0 for every LLM router, with no new prompt search. One format-only fix is allowed per model if the
  dev parse-failure rate is > 2%; it is logged.
- **Free routers.** Phase-1 grids, nested 5-fold CV. Regex is written by an agent under a 4 h timebox, with one
  optional, logged 2 h round.
- **Calibration.** Isotonic or Platt maps by CV Brier, applied only if `ece_cal < ece_raw`.
- **Cascade thresholds E7-L and E9-L.** Rule (a) of prereg-v1 §4: maximum joint subject to routing cost ≤ 0.5 ×
  the Sonnet 5 P0 dev-L cost per case. Grid 0.50..0.99, step 0.01. Cross-fitted on the dev-L shadow (Sonnet
  1 rep, dev only; OQ-1).
  - Fallback if OQ-1 = no: Sonnet is excluded from the shadow, E9-L's last step is replayed as "Jev decision"
    for threshold fitting, and this is logged as a design limitation.
- **Effort log:** `docs/tuning-effort-l.md`.

## 6. Run manifest outline (`config/study_manifest_l.yaml`; Part A in `config/addendum_manifest.yaml`)

Part A (test-v2), in priority order:

| Priority | Runs |
|---|---|
| 10 | E3c, E3t, E10c, E10t (1 rep) |
| 20 | E6m, E6n (1 rep) |
| 21 | E6m, E6n rep2 on 50 cases |
| 70 | `lat-*` blocks 1–4 × {E3c, E3t, E10c, E10t, E6m, E6n} + anchors {qwen, embedding, jev, haiku}, interleaved by block, `config/manifest/latency_test_v2_b*.ids` |

Part B (test-L), in priority order:

| Priority | Runs |
|---|---|
| 10 | Free routers 1 rep: E1, E2, E3, E3c, E3t, E10, E10c, E11; E1 repeat20 |
| 20 | Shadow tuned, 3 reps, **without Sonnet**: regex, bm25, embedding, classifier, hybrid, jev |
| 25 | E4 Jev 3 reps (H3-L); E6 Haiku 1 rep (H3-L); E6m 1 rep (H2-L); E6b Qwen 1 rep (H2-L, concurrency 1); E6n 1 rep |
| 30 | E9-L routing 3 reps; E7-L routing 3 reps |
| 40 | **E0-L e2e r1, E9-L e2e r1 (H1-L)** |
| 45 | E9-L-fullskill e2e r1 (S1) |
| 50 | Repeat checks: Haiku rep2 60, Qwen/8B rep2 50 |
| 70 | Latency blocks 1–4 × {regex, bm25, embedding, E3c, E3t, classifier, hybrid, jev, haiku, qwen, E6m, E6n, E7-L, E9-L}, `latency_test_l_b*.ids` |
| 80 | X2 paired subset, small profile (`mcp_url` :8765): E1, E2, E3, E10, E11, E4, E6m, E6 Haiku |
| 90 | Executor variance: E0-L, E9-L rep2 on 60 |

Each entry carries `config_hash`, `prompt_hash` and `catalog_hash`. The version guard asserts all three.

## 7. Budget

- **Phase-2 ledger mark:** AWS 52.11, OpenRouter 5.83.
- **Phase-2 cap:** US$ 40 total, of which the run caps are AWS ≤ 29.0 and OR ≤ 9.0.
- **Expected spend:** US$ 28.0, or 35.1 with 25% contingency. Per item: `.omc/plans/autopilot-impl.md` §5.
  At freeze: `docs/prereg/estimates-l.md`, with the a-priori upper bound and the expected value from the dev-L
  measured cost per case and per turn.
- **Guard:** it runs before every run. A refused run is a deviation and is reported as not run. Runs are never
  reordered.

## 8. Stopping and deviation rules

- No change to configs, prompts, labels, thresholds, calibration maps, catalog or scorers after the first row of
  the split they govern: test-v2 rows for Part A, test-L rows for Part B.
- Infra errors: up to 2 retries of the error rows. A run with > 2% errors is FLAGGED and redone from scratch,
  never patched.
- **Budget stop:** if the phase-2 ledger delta reaches US$ 38 before every priority-≤ 40 run is COMPLETE, stop
  and log a deviation. The primaries are reported with whatever is COMPLETE. An incomplete primary is reported
  as not run, never imputed.
- **Data stop:** if the test-L audit flags more than 40% of cases, stop before the tag and decide (logged) whether
  to regenerate the affected slots. This happens before freeze, so it is not a deviation.
- Label corrections after the run go into a separate rescore and never replace the analysis.
- Deviations are appended to `docs/prereg/deviations-v2.md` with a timestamp.

## 9. Analysis plan

1. **Part A.** `scripts/analysis/addendum_all.py` → `docs/results/addendum/`: family A (Holm), estimation tables,
   and latency with anchors. Phase-1 drift is reported as Δ p50/p95 of the anchors against the phase-1 lat-* values.
2. **Part B.** `scripts/analysis/final_l_all.py` → `docs/results/phase2/` (`primary.md`, `secondary.md`,
   `estimation.md`, `exploratory.md`, `enterprise_matrix_l.md`, figures). Every number is tagged [C], [E] or [X].
   H1-L is shown under both scorers.
3. **18 vs 62** (X1, X2) in `docs/results/phase2/catalog_size.md`, with the caveat repeated in every table caption.
4. **Write-up:** new pt-BR chapters in `estudos/` (catalog-size results, the cloud addendum, the updated enterprise
   matrix and threats to validity) plus the `docs/` mirror. Phase-1 chapters are not edited, apart from links.

## 10. Open items to resolve before freeze

- OQ-1: whether the dev-L shadow may include Sonnet 5 at 1 rep (~US$ 1.35) to fit the E9-L thresholds.
- OQ-2: whether S2 (the equivalence on the same-calls subset) stays a test, or becomes estimation if the subset is
  under 60 cases.
- OQ-3: the final per-skill quota of the orig subset (≥ 30% of single-label cases) against per-tool coverage of
  the new tools.

## Constraint update (2026-10-02, user decision, binding)

- **No local models.** No Ollama in phase 2 (no Qwen3-8B, no local qwen3-embedding): local inference
  would perturb performance/latency. Regex and BM25 (CPU, no model) stay. Local arms in comparisons
  are the EXISTING phase-1 rows (test-v2 accuracy, phase-1 lat-* latency), never re-run.
- **OpenRouter = Jev only** (`typesafe/jev-router`); balance US$ 3.91 reserved for it.
- **Everything else on Bedrock, cap US$ 40** (AWS). Dataset generation and audit move to Bedrock
  (`scripts/dataset/bedrock_chat.py`, same contract as `openrouter.chat_json`):
  - generator **`moonshotai.kimi-k2.5`** (Moonshot family: not a router, not an auditor);
  - auditors **`openai.gpt-oss-120b-1:0`** (OpenAI family, reasoning_effort low) and
    **`deepseek.v3.2`** (DeepSeek family): the same two families that audited test-v2.
  - Chosen by a pt-BR smoke on 2026-10-02 (Kimi produced the most natural colloquial pt-BR and a
    correctly labelled ambiguous case; GLM-5 mislabelled one).
- Semantic dedupe uses Bedrock Titan v2 (not the local embedder).
- Large-profile embedding/classifier/hybrid routers use Bedrock embeddings (Cohere v4 or Titan v2,
  whichever wins Part A dev CV). H2-L (managed vs local 8B) is re-specified: Ministral vs Haiku 4.5
  (NI, 3 pp), since no local arm runs on test-L.
