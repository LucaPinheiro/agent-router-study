# Part B secondary analyses [C]: families S-e2e and S-routing on `test_l`

Same machinery as primary.md; Holm within each family (a not-run hypothesis enters with p = 1; S5 and S6 are dropped: their reference arm is local and no local model runs in phase 2).

## Family S-e2e (Holm within) [C]

- **S1:** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, one-sided (confirms D-002 on a fresh split).
- **S2:** e2e_success_sym(E9-L) − e2e_success_sym(E0-L) on the cases where both arms executed the same sequence of business calls; equivalence ±3 pp (TOST, 90% CI inside). Same-calls cases: **225**.

| id | run | reference | kind | n cases | Δ pp [95% CI] (paired cluster bootstrap) | McNemar case-level run-only/ref-only | sign-flip p | Holm p (family) | reject @0.05 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | E9-full@e2e | E9@e2e | greater (margin 3 pp) | 300 | -0.3 [-2.7, 1.7] | 5/6 p=1 | 0.7256 | 0.7256 | no | CI includes 0 (no directional claim) |
| S2 | E9@e2e | E0@e2e | equivalence (margin 3 pp) | 225 | 1.8 [0.4, 3.6] | 4/0 p=0.125 | 0.07589 | 0.1518 | no | inconclusive |

## Family S-routing (Holm within) [C]

### S3: regex test-L − dev-L CV joint < 0 (magnitude with a CI; dev fixed; CI rule, no p-value)

| router | dev-L joint % | test joint % [95% CI] | gap pp [95% CI] | verdict |
|---|---|---|---|---|
| E1 regex | 82.7 | 56.3 [50.7, 62.0] | -26.4 [-32.0, -20.7] | gap < 0 (test CI entirely below dev) |

### S4-S7

- **S4:** Joint(E3 embedding, Bedrock Titan v2) − Joint(E1 regex), two-sided.
- **S5 (dropped):** Joint(E3c Cohere) − Joint(E3 LOCAL): no local arm on test-L.
- **S6 (dropped):** Joint(E6n Nemotron) − Joint(E6b Qwen3-8B LOCAL) > −3 pp: no local arm on test-L.
- **S7:** Joint(E10, best pre-declared probe) − Joint(E4 Jev), two-sided.

| id | run | reference | kind | n cases | Δ pp [95% CI] (paired cluster bootstrap) | McNemar case-level run-only/ref-only | sign-flip p | Holm p (family) | reject @0.05 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| S4 | E3 | E1 | two_sided | 300 | 3.7 [-3.3, 10.3] | 58/47 p=0.329 | 0.343 | 0.343 | no | CI includes 0 (no directional claim) |
| S5 | E3c | E3-local | two_sided | - | missing E3c: run missing or not COMPLETE |  |  | - | - | **DROPPED** (constraint update; out of the Holm family) |
| S6 | E6n | E6b | non_inferiority | - | missing E6b: no local model in phase 2 (constraint 2026-10-02): no Qwen3-8B arm on test-L |  |  | - | - | **DROPPED** (constraint update; out of the Holm family) |
| S7 | E10 | E4 | two_sided | 300 | -25.9 [-31.7, -20.0] | 11/94 p=1.39e-17 | 9.999e-05 | 0.0002 | yes | CI excludes 0 (run lower) |
