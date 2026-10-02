# Pre-registration prereg-v1: routing study, confirmatory split test-v2

Status: frozen by the annotated git tag `prereg-v1` (local). Written before any test-v2 call:
no router, executor or scorer has seen a test-v2 case. Source:
`.omc/reviews/methodology-final.md` §PRE-REGISTRATION, adapted to test-v2 (B1 option A),
`docs/decisions/2026-10-01-calibration-and-prompts.md` (binding), `.omc/plans/final-study-master.md`
Phase 4–5.

## 1. Frozen artifacts

| artifact | value |
|---|---|
| code | the commit tagged `prereg-v1` (`git rev-parse prereg-v1^{commit}`); the tree is clean at the tag |
| confirmatory data | `data/dataset_test_v2.jsonl`, 349 cases, sha256 `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66` (docs/dataset-card.md "Freeze": automated adjudication only) |
| exposed replication data | `data/dataset_test_v1.jsonl` → `dataset_test.jsonl`, sha256 `994d20623384931f9bf06ab9f3ee7028397118b66a7ff0abd800bffeef543a77` (free routers only) |
| dev data | `data/dataset_dev.jsonl`, sha256 `112fc7f0791e35cf1e250a40e362698212f029b4209b6ff7f33dc33717a8874a` (all tuning, selection and thresholds) |
| catalog content hash | `128584617807` (`Catalog.hash`, protocol-independent; MCP pinned at 2026-07-28) |
| scorer hash | `e0eef1fb0073` (`eval/scorers.py` + `eval/grounding.py`) |
| run prompt hash | `c61ad0a7b7f8` (`run_prompt_hash`: executor + router templates) |
| run manifest | `config/study_manifest.yaml`, sha256 `9e4cdb2626213dbb805ae54b0218b7cedd96d81fff920befc2c2c46282836868`; every entry carries its frozen `config_hash` / `prompt_hash`, asserted by `study run-manifest` |
| prompt selection | `config/prompt_selection.yaml`, sha256 `3648a71d90c0c6583b4ab27ce6a1bc7e856b2f29249ce92551e3eb2d34d980fb` |
| cascade thresholds | section 4; written into `config/experiments/e7–e9 (+e12)` |
| bootstrap | seed 20260930, 10 000 resamples, cluster (case) bootstrap |

Label audit: test-v2 labels are the **automated** blind audit adjudication (two non-Claude auditor
families, docs/dataset-card.md). Human review of the flagged cases (`data/audit/review.html`) is
optional; if done, it is reported as a **separate rescore** with its own dataset sha and never
replaces the pre-registered analysis.

Per-entry hashes (from `study run-manifest --dry-run` / `config_hash(load_settings(config,
patches=overrides))`):

| run | config | config_hash | prompt_hash |
|---|---|---|---|
| v2-e1-regex-routing-r1 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v2-e2-bm25-routing-r1 | e2_bm25.yaml | 7bb5a5960490 | c61ad0a7b7f8 |
| v2-e3-embedding-routing-r1 | e3_embedding.yaml | 1899b6f414a5 | c61ad0a7b7f8 |
| v2-e10-classifier-routing-r1 | e10_classifier.yaml | 616af886b783 | c61ad0a7b7f8 |
| v2-e11-hybrid-routing-r1 | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |
| v2-e1-regex-routing-repeat20 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v2-e3-embedding-qwen06b-routing-r1 | e3_embedding_qwen06b.yaml | 98ef77240be7 | c61ad0a7b7f8 |
| v2-e3-embedding-bgem3-routing-r1 | e3_embedding_bgem3.yaml | 3b95fe4e6beb | c61ad0a7b7f8 |
| v2-shadow-tuned-routing-r3 | e9_regex_jev_llm.yaml | cc01e0b06bb2 | c61ad0a7b7f8 |
| v2-e4-jev-canonical-routing-r3 | e4_jev.yaml | acd7ff96155b | c61ad0a7b7f8 |
| v2-e5-sonnet-canonical-routing-r3 | e5_llm_sonnet.yaml | 40c93f91f270 | c61ad0a7b7f8 |
| v2-e7-tuned-routing-r3 | e7_regex_jev.yaml | 4fbfd7133b32 | c61ad0a7b7f8 |
| v2-e9-tuned-routing-r3 | e9_regex_jev_llm.yaml | 8f5f721c9158 | c61ad0a7b7f8 |
| v2-e8-tuned-routing-r3 | e8_regex_llm.yaml | 755265ce73e0 | c61ad0a7b7f8 |
| v2-e6-haiku-canonical-routing-r1 | e6_llm_haiku.yaml | f6c0edce210b | c61ad0a7b7f8 |
| v2-e6-haiku-canonical-rep2-60 | e6_llm_haiku.yaml | f6c0edce210b | c61ad0a7b7f8 |
| v2-e6b-qwen-canonical-routing-r1 | e6b_llm_qwen3_local.yaml | 903a4a1e56d3 | c61ad0a7b7f8 |
| v2-e6b-qwen-canonical-repeat50 | e6b_llm_qwen3_local.yaml | 903a4a1e56d3 | c61ad0a7b7f8 |
| lat-regex-b1 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b1 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b1 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b1 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b1 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b1 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b1 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b1 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b1 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b1 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b1 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b1 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| lat-regex-b2 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b2 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b2 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b2 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b2 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b2 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b2 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b2 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b2 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b2 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b2 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b2 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| lat-regex-b3 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b3 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b3 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b3 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b3 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b3 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b3 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b3 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b3 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b3 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b3 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b3 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| lat-regex-b4 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b4 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b4 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b4 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b4 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b4 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b4 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b4 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b4 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b4 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b4 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b4 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| v2-e0-native-e2e-r1 | e0_native.yaml | 93c7c3ea1e02 | c61ad0a7b7f8 |
| v2-e9-tuned-e2e-r1 | e9_regex_jev_llm.yaml | 8f5f721c9158 | c61ad0a7b7f8 |
| v2-e1-regex-e2e-r1 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v2-e5-sonnet-canonical-e2e-r1 | e5_llm_sonnet.yaml | 40c93f91f270 | c61ad0a7b7f8 |
| v2-e7-tuned-e2e-r1 | e7_regex_jev.yaml | 4fbfd7133b32 | c61ad0a7b7f8 |
| v2-e6b-qwen-canonical-e2e-r1 | e6b_llm_qwen3_local.yaml | 903a4a1e56d3 | c61ad0a7b7f8 |
| v2-e0-native-e2e-rep2-60 | e0_native.yaml | 93c7c3ea1e02 | c61ad0a7b7f8 |
| v2-e9-tuned-e2e-rep2-60 | e9_regex_jev_llm.yaml | 8f5f721c9158 | c61ad0a7b7f8 |
| v2-e11-hybrid-e2e-r1 | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |
| rq5-test_v2-regex-base | e1_regex.yaml | 094189076dc4 | c61ad0a7b7f8 |
| rq5-test_v2-regex-zero | e1_regex.yaml | 369d4719b479 | c61ad0a7b7f8 |
| rq5-test_v2-regex-eng | e1_regex.yaml | 8136ba8c282c | c61ad0a7b7f8 |
| rq5-test_v2-regex-full | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| rq5-test_v2-bm25-base | e2_bm25.yaml | c8d6844e3901 | c61ad0a7b7f8 |
| rq5-test_v2-bm25-zero | e2_bm25.yaml | 7db75b6e764a | c61ad0a7b7f8 |
| rq5-test_v2-classifier-base | e10_classifier.yaml | 6194aad1119c | c61ad0a7b7f8 |
| rq5-test_v2-classifier-zero | e10_classifier.yaml | 77e7a5a727b2 | c61ad0a7b7f8 |
| rq5-test_v2-embedding-base | e3_embedding.yaml | 5418975870b9 | c61ad0a7b7f8 |
| rq5-test_v2-embedding-zero | e3_embedding.yaml | 46dc0103343b | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-base | e11_hybrid.yaml | af686213038b | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-zero | e11_hybrid.yaml | c1edc8996a71 | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-eng | e11_hybrid.yaml | 2eb0483c43a8 | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-full | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |
| rq5-test_v2-jev-base | e4_jev.yaml | ea0f9ccdb142 | c61ad0a7b7f8 |
| rq5-test_v2-jev-zero | e4_jev.yaml | 888e3c0ba3c8 | c61ad0a7b7f8 |
| rq5-test_v2-haiku-base | e6_llm_haiku.yaml | 2d76d848e40b | c61ad0a7b7f8 |
| rq5-test_v2-haiku-zero | e6_llm_haiku.yaml | 8dd1d7028c32 | c61ad0a7b7f8 |
| rq5-test_v2-sonnet-base | e5_llm_sonnet.yaml | 9b17371e0cb3 | c61ad0a7b7f8 |
| rq5-test_v2-sonnet-zero | e5_llm_sonnet.yaml | dbd6461926df | c61ad0a7b7f8 |
| x-e4-jev-p6c-routing-r1 | e4_jev.yaml | 7e8c24a4c406 | c61ad0a7b7f8 |
| x-e12-hybrid-tuned-routing-r3 | e12_hybrid_jev_llm.yaml | feff62642c5e | c61ad0a7b7f8 |
| v1-e1-regex-routing-r1 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v1-e2-bm25-routing-r1 | e2_bm25.yaml | 7bb5a5960490 | c61ad0a7b7f8 |
| v1-e3-embedding-routing-r1 | e3_embedding.yaml | 1899b6f414a5 | c61ad0a7b7f8 |
| v1-e10-classifier-routing-r1 | e10_classifier.yaml | 616af886b783 | c61ad0a7b7f8 |
| v1-e11-hybrid-routing-r1 | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |

## 2. Routers and tracks

| exp | router | prompt (both tracks) | calibration map applied (decision rule `ece_cal < ece_raw`) |
|---|---|---|---|
| E5 | Sonnet 5 (Bedrock) | P0 | skill yes (0.111→0.091), tool no (0.036→0.056) |
| E6 | Haiku 4.5 (Bedrock) | P0 | none (skill 0.058→0.063, tool 0.055→0.061) |
| E6b | Qwen3-8B q8_0 (Ollama, thinking off) | P0 | skill yes (0.045→0.041), tool yes (0.116→0.032) |
| E4 | Jev (OpenRouter) | P0 | skill yes (0.063→0.024), tool no (0.047→0.058) |

- One-SE rule (5-fold CV on dev, ITT) picked P0 for every model on both tracks, and P0 as the
  canonical prompt over the four models (P0 80.2, P0+P4 81.2 mean CV joint). Therefore **track B
  (tuned) == track A (canonical)** for every LLM-type router: no `*_tuned` config and no duplicate
  run exists. The argmax alternatives (Sonnet/Haiku/Qwen P0+P4, Jev P0+P5/P6c) are dev-only
  sensitivity (docs/prompt-apex.md); Jev P0+P6c is run once as an exploratory cost variant.
- Free routers: E1 regex, E2 BM25, E3 embedding (qwen3-embedding 8B; 0.6B and bge-m3 ablations),
  E10 classifier (linear probe), E11 hybrid (regex + classifier convex fusion); configs and maps
  as committed (docs/tuning-effort.md).
- Cascades E7 (regex → Jev), E8 (regex → Sonnet), E9 (regex → Jev → Sonnet; Jev → Sonnet at the
  tool stage) on the tuned track (= P0); E12 (hybrid → Jev → Sonnet) exploratory.
- Response cache: Sonnet, Haiku, Qwen and Jev decisions are cached per (case, rep, rendered
  prompt). The test-v2 shadow pass runs first; E4, E5 and E7–E9 reuse its samples (paired by
  construction). Reps remain independent samples (the rep index is part of the key).

## 3. Unit of analysis and handling

- Unit: the case. Scores are averaged over reps per case before any test.
- ITT: a failed routing stage (error, parse failure with no accepting step) is **wrong**, never an
  abstention; error rate is reported per run. The error-free intersection is a sensitivity only.
- Out of scope: `__global__` + `escalate_to_human` counts as abstention (`scorers.py`).
- Multi-label: any acceptable label counts. First-label-only (`joint_first_label`) is a
  sensitivity; ambiguo labels are weak (auditor A accepted 23/70), so ambiguo is also reported
  separately.
- Primary routing metric: **joint top-1 accuracy** (routing-only). Primary e2e metric:
  **e2e_success** (decomposed into first_call_success / clarification_credited /
  recovered_credited).

## 4. Cascade thresholds (D5)

Method, declared before the dev shadow run (results/freeze/DECISIONS.log, 2026-10-01T12:01:37-03:00):
**(a) maximum joint accuracy subject to routing cost ≤ 0.5 × the Sonnet 5 P0 dev cost per case**
(5.975 US$/1k → budget US$ 0.0029875/case), over the grid 0.50..0.99 step 0.01 per non-last step,
ties → lower cost, then higher thresholds; fitted on all dev rows of the dev shadow pass with the
final configs (`freeze-dev-shadow-r1`, ITT), honest estimate by 5-fold cross-fitting. Rationale:
the operating point is tied to H1's co-primary (cost ratio < 0.5). The precision rule (b) is
reported as a sensitivity only (unstable per fold at n = 151).

| exp | skill pipeline (min_confidence) | tool pipeline | dev joint % | CV held-out joint % [95% CI] | CV US$/1k routing |
|---|---|---|---|---|---|
| E7 | regex 0.81 → Jev | Jev | 79.5 | 78.8 [72.2, 85.4] | 0.865 |
| E8 | regex 0.88 → Sonnet (fallback: budget infeasible, (a) unconstrained) | Sonnet | 78.8 | 78.1 [71.5, 84.8] | 5.14 |
| E9 | regex 0.88 → Jev 0.76 → Sonnet | Jev 0.50 → Sonnet | 80.1 | 77.5 [70.9, 84.1] | 1.28 |
| E12 (exploratory) | hybrid 0.83 → Jev 0.77 → Sonnet | Jev 0.50 → Sonnet | 80.1 | 78.1 [71.5, 84.8] | 1.19 |

Dev references (all rows, no fit; docs/results/cascade-thresholds-dev.md, Pareto front in
docs/results/cascade-pareto-dev.csv):

| exp | always-last (final router alone) | always-first | oracle stopping step | random deferral at (a)'s rates | precision rule (b), CV |
|---|---|---|---|---|---|
| E7 | 76.8 @ 0.94 $/1k | 75.5 @ 0.82 | 80.8 @ 0.57 | 75.9 @ 0.85 | 76.2 @ 0.82 |
| E8 | 76.8 @ 5.92 | 74.2 @ 4.66 | 80.1 @ 3.71 | – | 74.2 @ 4.68 |
| E9 | 76.8 @ 6.86 | 75.5 @ 0.82 | 83.4 @ 0.88 | 76.1 @ 1.11 | 76.2 @ 0.94 |
| E12 | 76.8 @ 6.86 | 77.5 @ 0.79 | 83.4 @ 0.83 | 77.4 @ 0.98 | 77.5 @ 0.91 |

Provenance of the dev shadow: `freeze-dev-shadow-r1` (config/freeze_dev_manifest.yaml), 151/151
rows, 0 errors, catalog 128584617807, scorer e0eef1fb0073, code b76b3b1 + uncommitted drafts of
the manifest and this document only (no src/config change). A first attempt was FLAGGED (5 rows,
3.3%, AWS ExpiredToken) and redone from scratch under the operations rule; the flagged files are
kept in results/freeze/superseded/. The E8 fallback was decided after a preview calibration on
that flagged attempt (logged, docs/prereg/decisions-log.txt); E7/E9/E12 follow the rule declared
before any shadow row.

## 5. Hypotheses

### Primary (confirmatory; Holm across H1–H3; α = 0.05)

- **H1 (RQ3, cascade non-inferiority).** Joint(E9) − Joint(E5 Sonnet) > −3 pp, where E5 is the
  canonical run (= tuned, same prompt bytes). Decision: the lower bound of the two-sided 95%
  paired cluster-bootstrap CI of Δ (one-sided 97.5%) exceeds −3 pp; p = case-level sign-flip with
  shift 0.03. Co-primary (estimation with CI): routing US$/1k ratio E9/E5 (observed-cache regime)
  < 0.5.
- **H2 (RQ3, free-first cascade).** Joint(E7) − Joint(E5) > −3 pp, same test.
- **H3 ("vale ter roteador?", e2e).** e2e_success(E9) − e2e_success(E0), two-sided paired Δ with
  95% CI; directional claim only if the CI excludes 0 (expected MDE ≈ 5–7 pp). Cost per turn
  E9/E0 with CI.

### Secondary (Holm within each family)

- **S1 (prompt engineering).** Joint(tuned) − Joint(canonical) ≥ 0 per LLM router. Since the
  pre-declared one-SE rule chose the same prompt for both tracks on every router, Δ ≡ 0 by
  construction and **no S1 test is run on test-v2**; the finding is "the selection procedure
  found no tuning worth applying" (reported with the dev nested estimates and the argmax
  sensitivity). This is a consequence of the pre-declared rule, not a dropped hypothesis.
- **S2 (model vs model, canonical track).** Paired Δ joint for Haiku 4.5, Qwen3-8B and Jev vs
  Sonnet 5; TOST ±3 pp (90% CI inclusion); conclusions "equivalent", "not equivalent" or
  "inconclusive" only.
- **S3 (dev → test generalization).** Test-v2 joint minus dev CV joint for regex (dev 84.8,
  rules written on dev) and BM25 (dev fixed 55.7). Hypothesis: regex gap < 0. Magnitude with CI
  (test CI; the dev number is treated as fixed).
- **S4 (lexical vs semantic).** Joint(E3 embedding) − Joint(E1 regex), two-sided.

### Estimation only (CIs, no tests)

Per strategy: skill %, conditional tool %, recall@1/2/3, error rate, rep-flip rate (Haiku 60,
Qwen 50, regex 20); ECE and Brier on test (raw and dev-calibrated); cost/1k in three regimes
(observed warm cache, list price uncached, modelled cache hit rate vs QPS with 5-min TTL);
latency p50/p95 **from the dedicated benchmark only** (cold first case and warm reported
separately); cascade coverage per step; abstention precision/recall; e2e decomposition,
e2e_strict, args_invented, entity_grounded; executor variance (E0, E9 on 60 cases); per
category, per tool, single vs multi-label; E10 classifier, E11 hybrid, E8, embedder ablations.

### Exploratory (labelled as such)

Alternative threshold method (b) and the whole dev Pareto front replayed on the test-v2 shadow;
E12 (hybrid → Jev → Sonnet); Jev P0+P6c cost variant; RQ5 leave-tools-out (`docs/rq5-design.md`,
not promoted); test-v1 free-router replication (exposed split, contamination check);
top-k/history ablations; served-model analysis for Jev; context economics per prompt variant.

## 6. Run plan, order and budget

Executed only by `uv run study run-manifest config/study_manifest.yaml` in priority order with
`BUDGET__AWS_USD_CAP=85` (90 − 5 margin) and `BUDGET__OPENROUTER_USD_CAP` = ledger OpenRouter
total at launch + 4.0 (balance − 0.5). Budget at freeze: AWS spent 17.6345 of 90,
OpenRouter 4.4031 of 9.

Totals (102 entries; per-entry table in docs/prereg/estimates.md):

| | a priori upper bound (`study estimate`, no cache) | expected (dev $/case, cache sharing, e2e ×1.3) | ceiling |
|---|---|---|---|
| AWS (Bedrock) | 221.69 | 50.07 | 90 − 17.63 − 5 = **67.37** |
| OpenRouter | 0.00 (Jev has no list price) | 1.68 | 9 − 4.40 − 0.5 = **4.10** |

The a-priori bound assumes no cache and maximum completions (each e2e run 25–27 US$); it is
not a forecast. The guard checks each run on its own before it starts (measured cost when
rows of the config exist, else the bound): at the expected spend every primary run is admitted
under the 85 US$ cap; the lowest-priority e2e entry (E11, 84) is the one the guard may refuse.

## 7. Operations, retry and abort rules (B6)

- Infra errors: up to 2 retries of the error rows, same config (`max_infra_retries: 2`).
- A run with > 2% error rows after the retries is FLAGGED: stop, fix the infrastructure, redo that
  run from scratch (never partially patched). Never re-run for any other reason.
- The budget guard (measured cost per turn × missing turns, else the a-priori upper bound) runs
  before every run; a refused run is logged as a deviation and reported as not run. Runs are
  never reordered to fit the budget.
- Langfuse unavailable → the manifest stops before spending (preflight).
- Local runs (Qwen, embedder): one resident Ollama model, concurrency 1 for Qwen.

## 8. Stopping and deviation rules

- No config, prompt, label, threshold or scorer change after the first test-v2 row.
- Every deviation is appended with a timestamp to `docs/prereg/deviations.md` and reported.
- Label corrections found after the run (including the optional human review) are a separate
  rescore, never a replacement of the pre-registered analysis.
- Results of test-v2 are analysed with `study report --manifest config/study_manifest.yaml
  --split test_v2` and the contrasts listed in the manifest (families H, S2, S4).
