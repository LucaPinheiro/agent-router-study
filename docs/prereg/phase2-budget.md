# Phase-2 budget mark (plan T0.2)

Every phase-2 cost is measured against this start mark. Phase-2 spend = ledger total − mark.
The ledger is `results/spend_ledger.jsonl`, read with `uv run study budget`.

## Start mark

| provider | mark (US$) | ledger at the mark |
|---|---|---|
| AWS (Bedrock) | **52.11** | 52.1147 |
| OpenRouter | **5.83** | 5.8345 |

The mark is the ledger at **2026-10-01T23:42:38Z**: the last phase-1 call before the phase-2 work
started. Recomputing the cumulative ledger sum up to that row gives 52.1147 / 5.8345, which matches
the mark at cent precision.

## Caps (plan §5)

| | phase-2 cap (US$) | ledger ceiling = mark + cap |
|---|---|---|
| AWS | 29.00 | **81.11** |
| OpenRouter | 9.00 | **14.83** |
| total | 38.00 (US$ 2 reserve under the US$ 40 limit) | |

The OpenRouter account cap in the settings is still **9.00 absolute**, which is the phase-1 value.
Phase-2 OpenRouter work therefore stops at about US$ 3.16 of phase-2 spend unless that cap is
raised to the ceiling (14.83) when the human top-up lands. The plan's hard gate (R4) says T4.1
does not start until the balance is ≥ 9.5.

## Item caps (plan §5, expected US$)

| ID | Item | AWS | OR |
|---|---|---|---|
| A1 | Part A dev tuning, 8B ×2 (151) | 0.20 | – |
| A2 | Part A embeddings (dev grid + test-v2 + latency) | 0.10 | – |
| A3 | Part A test-v2 8B ×2 (349 + rep2 50) | 0.50 | – |
| A4 | Part A latency (6 new × 100 + anchors) | 0.65 | 0.08 |
| A5 | Phase-1 symmetric re-score (offline) | 0 | 0 |
| B1 | dev-L + test-L generation (450 accepted) | – | 2.00 |
| B2 | Audit dev-L + test-L | – | 2.25 |
| B3 | Host smoke + dev-L e2e smoke (5 + 20 turns) | 0.45 | – |
| B4 | dev-L Haiku P0 1 rep | 1.17 | – |
| B5 | dev-L Jev P0 1 rep (shadow) | – | 0.19 |
| B6 | dev-L Sonnet shadow 1 rep (thresholds only) | 1.35 | – |
| B7 | dev-L 8B ×2 + cloud embeddings | 0.28 | – |
| B8 | dev-L e2e validation E0-L + E9-L (40 + 40) | 0.81 | – |
| B9 | test-L Jev E4 3 reps | – | 1.12 |
| B10 | test-L Haiku 1 rep + rep2 60 | 2.81 | – |
| B11 | test-L 8B ×2, 1 rep + rep2 50 | 0.66 | – |
| B12 | test-L E9-L routing 3 reps | 1.40 | – |
| B13 | test-L E0-L e2e (H1) | 3.39 | – |
| B14 | test-L E9-L e2e (H1) | 2.69 | – |
| B15 | test-L E9-L-fullskill e2e (S1) | 2.80 | – |
| B16 | Executor variance rep2 on 60 | 1.22 | – |
| B17 | test-L latency | 1.17 | 0.12 |
| B18 | Paired catalog-size subset (~90 cases) | 0.55 | 0.08 |
| | **Expected total** | **22.20** | **5.84** |

Expected US$ 28.0 in total, or 35.1 with 25% contingency. If a cap is hit, the guard refuses the
run and nothing is reordered. Drop order: B16, then B15, then B18-Haiku, then the A4/B17 anchors.

## Ledger capture at the time of writing (2026-10-01, `uv run study budget`)

```
aws         (bedrock) spent $52.2938 of cap $90.00
openrouter  (openrouter) spent $5.8395 of cap $9.00
```

Spend since the mark (cumulative ledger rows after 2026-10-01T23:42:38Z):

| provider | run | calls | US$ | counts as |
|---|---|---|---|---|
| bedrock | `obs-graph-check` (phase-1 Langfuse verification, dev) | 4 | 0.0356 | phase-1 tail |
| bedrock | `it-trace-1790904935` (integration test) | 8 | 0.0380 | phase-1 tail |
| openrouter | `it-trace-1790904935` | 4 | 0.0050 | phase-1 tail |
| bedrock | phase-2 smoke calls (8B routers, Cohere/Titan, no run name) | 765 | 0.0045 | phase 2 (T0.3/T2.1) |
| bedrock | `p2-dev-e6c_llm_ministral_bedrock` | 302 | 0.0677 | phase 2 (A1) |
| bedrock | `p2-dev-e6d_llm_nemotron_bedrock` | 301 | 0.0341 | phase 2 (A1) |

The capture differs from the mark only by these rows: 52.1147 + 0.0736 + 0.1063 = 52.2946 ≈
52.2938, within US$ 0.001 (the per-group sums are rounded to 4 decimals). For OpenRouter,
5.8345 + 0.0050 = 5.8395. Phase-2 spend so far is AWS US$ 0.106 and OpenRouter US$ 0. The
US$ 0.079 of phase-1 tail after the mark is also charged against the phase-2 caps, because the
caps are measured from the mark.
