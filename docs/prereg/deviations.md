# Deviations from prereg-v1

Append one entry per deviation: ISO timestamp, run, what changed, why, and its effect on the
pre-registered analysis. Empty at the tag.

## D-001 — 2026-10-01T15:18:56-03:00
- **Run:** v2-e3-embedding-bgem3-routing-r1 (manifest aborted before its first case; 7 runs already COMPLETE with 0 errors and unaffected).
- **What changed:** infra-only fix in `src/routing_study/llm.py` (`_check_ollama`): model-name comparison now normalizes Ollama's implicit `:latest` tag (`bge-m3` == `bge-m3:latest`). No config, prompt, label, catalog or scorer change; config_hash/prompt_hash of every run unchanged.
- **Why:** the pre-flight model check rejected a pulled model and aborted the whole manifest.
- **Effect on analysis:** none (no test_v2 row was produced or altered by the failing check). Manifest resumed; completed runs are skipped by key.
