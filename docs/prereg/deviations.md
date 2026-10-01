# Deviations from prereg-v1

Append one entry per deviation: ISO timestamp, run, what changed, why, and its effect on the
pre-registered analysis. Empty at the tag.

## D-001 — 2026-10-01T15:18:56-03:00
- **Run:** v2-e3-embedding-bgem3-routing-r1 (manifest aborted before its first case; 7 runs already COMPLETE with 0 errors and unaffected).
- **What changed:** infra-only fix in `src/routing_study/llm.py` (`_check_ollama`): model-name comparison now normalizes Ollama's implicit `:latest` tag (`bge-m3` == `bge-m3:latest`). No config, prompt, label, catalog or scorer change; config_hash/prompt_hash of every run unchanged.
- **Why:** the pre-flight model check rejected a pulled model and aborted the whole manifest.
- **Effect on analysis:** none (no test_v2 row was produced or altered by the failing check). Manifest resumed; completed runs are skipped by key.

## D-002 — 2026-10-01T19:45:50-03:00
- **Runs:** x-e9-fullskill-e2e-r1, x-e7-fullskill-e2e-r1 (config/study_manifest_explore.yaml), launched after the pre-registered manifest completes.
- **What:** EXPLORATORY, post-hoc. Same E9/E7 configs with `routing.tool.expose_top_k: 5` (route the skill, expose all 5 skill tools + globals to the executor).
- **Why:** the pre-registered H3 result (E9 e2e_success 45.8% vs native E0 55.6%) with E5 matching E0 on first-call tool (75.1%) suggests that hiding helper tools from the executor, not routing error alone, drives the e2e gap. Hypothesis generated after seeing test-v2 results.
- **Effect on analysis:** none on H1–H3/S1–S4 (pre-registered results unchanged). Reported only as an exploratory, hypothesis-generating comparison on the same test split (not confirmatory; any claim needs a fresh split).

## D-003 — 2026-10-01T20:21:04-03:00
- **Runs:** v1-* (EXPLORATORY test-v1 free-router replication); main manifest stopped at v1-e1-regex-routing-r1 before its first case. All confirmatory and estimation runs were already COMPLETE.
- **What changed:** infra-only (`eval/runner.py`): split `test_v1` (a symlink to the original `dataset_test.jsonl`) uploads to the existing Langfuse dataset `routing-study-test`, because Langfuse dataset item ids are unique per project and those ids already belong to that dataset. No config/prompt/label/scorer change.
- **Effect on analysis:** none; the v1 runs resume from scratch.
