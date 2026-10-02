# Deviations from prereg-v2a / prereg-v2

Append one entry per deviation: ISO timestamp, run, what changed, why, and its effect on the
pre-registered analysis (prereg-v2a §7).

## DV2-001 — 2026-10-02T00:43:34-03:00
- **Runs:** none (analysis naming only).
- **What changed:** prereg-v2a §8 names the analysis script `scripts/analysis/addendum_all.py` writing to `docs/results/addendum/`; the T2.6 task implemented it as `scripts/analysis/addendum_a.py` writing to `docs/results/addendum-a/` (and figures `estudos/figuras/final-a-*.png`).
- **Why:** coordinator task specification (T2.6), to keep the Part-A outputs apart from a later Part-B analysis.
- **Effect on analysis:** none. Same hypotheses (A1-A4, Holm), same machinery (paired cluster bootstrap 10k, seed 20260930, sign-flip p), same estimation list; every row's catalog/config/prompt hash asserted as in §8.

## D-L01 — 2026-10-02T10:11:44-03:00
- **Runs:** `config/study_manifest_l.yaml` (prereg-v2, test-L), stopped during `l-shadow-tuned-routing-r3` (the cache-filling shadow pass; not an analysed arm) and resumed by (case, rep). Every other run started after the resume.
- **What changed:** infra-only. At 10:08:19 the app-redis child process was OOM-killed during an AOF rewrite fork; auto-aof-rewrite and RDB save were disabled for the run (`results/phase2b/redis-restore.sh`). At 10:11:44 app-redis itself was OOM-killed (Docker VM 8.3 GB) by ~811k stale LangGraph checkpoint keys (~2 GB) left by earlier runs. The manifest was stopped; the `checkpoint*` / `write_keys_zset` keys were deleted with the user's approval (every result already lives in `results/*.jsonl`), Redis went from 2.05 GB to 141 MB, and the manifest was resumed. The shadow run's 66 error rows from the crash window (7.3%) were retried once by the runner's pre-registered retry rule (prereg-v2 §7: up to 2 retries of the error rows) and ended COMPLETE with 0 errors. The Redis config was restored after the manifest finished (12:36:52). Log: `results/phase2b/launch.log`, `results/phase2b/run-manifest.log`.
- **Why:** the host's LangGraph checkpointer keeps per-thread state in Redis; nothing ever expired the phase-1 / Part-A / dev-L checkpoints.
- **Effect on analysis:** none. No config, prompt, label, catalog, threshold, scorer, manifest, id file or `phase2_b.py` change; every `config_hash` / `prompt_hash` / `catalog_hash` is the frozen one (asserted on every row by `phase2_b.py`). Final state: 73/73 runs COMPLETE, 0 error rows in the manifest log. LangGraph checkpoints are per-turn conversation state, not results; no analysed row depends on a deleted key.
