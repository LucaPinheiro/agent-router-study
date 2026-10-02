# Secondary analyses (prereg-v1 S1-S4) on test-v2

Same machinery as primary.md (paired cluster bootstrap, 10k, seed 20260930; sign-flip p; Holm within family). ITT (an error row is wrong). Error rows after rescore: E4 2; E4-P6c 1 (all others 0).

## S1 (prompt engineering, tuned - canonical): DEGENERATE by construction

The pre-declared one-SE rule (5-fold CV on dev, ITT) selected P0 for both tracks of every LLM-type router, so tuned == canonical byte-for-byte and Δ ≡ 0: **no S1 test is run on test-v2** (pre-registered, not a dropped hypothesis). Finding: *the selection procedure found no prompt tuning worth applying*. Dev evidence (config/prompt_selection.yaml, docs/prompt-apex.md):

| model | canonical | tuned | nested-CV joint % (tuned) mean ± SD | nested outer-fold picks | plain-argmax sensitivity (dev only) |
|---|---|---|---|---|---|
| Sonnet 5 | P0 | P0 | 77.5 ± 9.8 | P0, P0, P0, P0, P0 | P0+P4 |
| Haiku 4.5 | P0 | P0 | 81.5 ± 3.8 | P0+P4, P0, P0, P0, P0 | P0+P4 |
| Jev | P0 | P0 | 78.2 ± 9.4 | P0, P0, P0, P0, P0 | P0+P5 |
| Qwen3-8B | P0 | P0 | 81.5 ± 3.2 | P0, P0, P0+P4, P0, P0 | P0+P4 |

Over the four models the canonical candidates on full dev had mean CV joint P0 80.2, P0+P4 81.2 (one-SE rule kept P0). The argmax alternatives are dev-only sensitivities and were not run on test-v2 (except Jev P0+P6c, exploratory cost variant; see estimation.md if complete).

## S2 (model vs model, canonical track): TOST ±3 pp vs Sonnet 5 (E5)

| id | run | reference | kind | n cases | Δ pp [95% CI] | McNemar case-level | TOST p (max of 2 one-sided) | Holm p (S2) | reject @0.05 | verdict (90% CI inside ±3 pp) |
|---|---|---|---|---|---|---|---|---|---|---|
| S2 Haiku 4.5 | E6 | E5 | equivalence (margin 3 pp) | 349 | 0.4 [-2.9, 3.6] | 20/17 p=0.743 | 0.06189 | 0.1311 | no | inconclusive |
| S2 Qwen3-8B | E6b | E5 | equivalence (margin 3 pp) | 349 | -4.2 [-8.1, -0.2] | 21/34 p=0.105 | 0.7233 | 0.7233 | no | inconclusive |
| S2 Jev | E4 | E5 | equivalence (margin 3 pp) | 349 | 0.6 [-2.1, 3.2] | 16/13 p=0.711 | 0.0437 | 0.1311 | no | equivalent |

90% paired CIs used for the TOST verdict: S2 Haiku 4.5: -2.4 to 3.1 pp; S2 Qwen3-8B: -7.5 to -0.9 pp; S2 Jev: -1.6 to 2.8 pp.

Note: E6 Haiku and E6b Qwen have 1 rep, E5 has 3 (per-case means); the paired Δ is over the 349 shared cases.

Reading: the pre-registered conclusion is the CI-inclusion rule on the unadjusted 90% paired CI. Under Holm within S2 (family-wise α 0.05) a pair is declared equivalent only if its TOST p, Holm-adjusted, is < 0.05. Where the two disagree (CI rule says equivalent, Holm p ≥ 0.05) the conservative reading is *equivalence not established after multiplicity control*; both are shown and neither is preferred post hoc.

S2 sensitivity: cases error-free in both runs (349, 349, 347 cases)

| id | run | reference | kind | n cases | Δ pp [95% CI] | McNemar case-level | TOST p (max of 2 one-sided) | Holm p (S2) | reject @0.05 | verdict (90% CI inside ±3 pp) |
|---|---|---|---|---|---|---|---|---|---|---|
| S2 Haiku 4.5 | E6 | E5 | equivalence (margin 3 pp) | 349 | 0.4 [-2.9, 3.6] | 20/17 p=0.743 | 0.06189 | 0.1238 | no | inconclusive |
| S2 Qwen3-8B | E6b | E5 | equivalence (margin 3 pp) | 349 | -4.2 [-8.1, -0.2] | 21/34 p=0.105 | 0.7233 | 0.7233 | no | inconclusive |
| S2 Jev | E4 | E5 | equivalence (margin 3 pp) | 347 | 0.5 [-2.2, 3.2] | 16/13 p=0.711 | 0.0343 | 0.1029 | no | equivalent |

## S3 (dev -> test generalisation): test-v2 joint - dev CV joint

Dev numbers are fixed by the pre-registration (regex 84.8 = dev joint of the rules written on dev; BM25 55.7 = dev fixed-config joint); the CI is the test-v2 cluster-bootstrap CI shifted by the fixed dev value (dev uncertainty ignored, as pre-registered). Hypothesis: regex gap < 0.

| router | dev joint % | test-v2 joint % [95% CI] | gap pp [95% CI] | verdict |
|---|---|---|---|---|
| regex (rules written on dev) | 84.8 | 52.7 [47.3, 57.9] | -32.1 [-37.5, -26.9] | gap < 0 (test CI entirely below dev) |
| BM25 (dev fixed) | 55.7 | 49.0 [43.8, 54.2] | -6.7 [-11.9, -1.5] | gap < 0 (test CI entirely below dev) |

## S4 (lexical vs semantic): E3 embedding - E1 regex, two-sided

| id | run | reference | kind | n cases | Δ pp [95% CI] | McNemar case-level | sign-flip p | Holm p (S4, 1 test) | reject @0.05 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| S4 embedding - regex | E3 | E1 | two_sided | 349 | 20.9 [15.2, 26.6] | 96/23 p=8.54e-12 | 9.999e-05 | 9.999e-05 | yes | CI excludes 0 |
