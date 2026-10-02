# Deviations from prereg-v2a / prereg-v2

Append one entry per deviation: ISO timestamp, run, what changed, why, and its effect on the
pre-registered analysis (prereg-v2a §7).

## DV2-001 — 2026-10-02T00:43:34-03:00
- **Runs:** none (analysis naming only).
- **What changed:** prereg-v2a §8 names the analysis script `scripts/analysis/addendum_all.py` writing to `docs/results/addendum/`; the T2.6 task implemented it as `scripts/analysis/addendum_a.py` writing to `docs/results/addendum-a/` (and figures `estudos/figuras/final-a-*.png`).
- **Why:** coordinator task specification (T2.6), to keep the Part-A outputs apart from a later Part-B analysis.
- **Effect on analysis:** none. Same hypotheses (A1-A4, Holm), same machinery (paired cluster bootstrap 10k, seed 20260930, sign-flip p), same estimation list; every row's catalog/config/prompt hash asserted as in §8.
