# Phase-1 e2e under the symmetric scorer (EXPLORATORY)

**Every number on this page is EXPLORATORY.** The symmetric scorer (`src/routing_study/eval/scorers_sym.py`, prereg-v2 §4) was designed after the phase-1 test-v2 results were seen (the 22/40 same-calls finding in `exploratory_e2e.md` §2). It is re-applied here OFFLINE to the recorded phase-1 rows, at zero API cost. The confirmatory phase-1 verdict (prereg-v1 H3, legacy scorer `e0eef1fb0073`) is **not** changed: E0 > E9.

What changes: the legacy scorer takes the e2e skill from the ROUTER's label in routed runs and from behaviour (`load_skill`) in E0. The symmetric scorer takes it from behaviour in both arms: the skill of the first skill-bound business tool the server executed; with no call, the skill of the tool credited by a clarification (inferred from the question, never from the router's tool); escalation-only or host abstention = `__abstain__`; only global calls = `__global__`; no action = `__abstain__`. It never reads `native`, the router's skill/tool or `resolved_by`. Everything else (args, completion, recovery, decomposition) is the legacy code.

Statistics: identical to primary.md. Unit = case (reps averaged first); paired cluster bootstrap over case ids, 10000 resamples, seed 20260930; exact McNemar on per-case majorities; two-sided sign-flip p, **unadjusted**. Intention to treat (no e2e run had an error row). Legacy numbers are read from `results/rescored/`, symmetric ones from `results/rescored-sym/`, both rescored from the same raw files (sha256 checked).

## 1. H3 (E9 − E0) under both scorers

| scorer | E9 e2e_success % [95% CI] | E0 e2e_success % [95% CI] | Δ E9 − E0 pp [95% CI] | McNemar E9-only / E0-only | sign-flip p (unadjusted) |
|---|---|---|---|---|---|
| legacy (pre-registered, confirmatory in phase 1) | 45.8 [40.4, 51.0] | 55.6 [50.1, 60.7] | **-9.7 [-13.5, -6.0]** | 6 / 40 (p=3.1e-07) | 9.999e-05 |
| symmetric (EXPLORATORY) | 53.0 [47.6, 58.2] | 56.2 [50.7, 61.3] | **-3.2 [-6.0, -0.3]** | 7 / 18 (p=0.0433) | 0.0425 |

Legacy reproduces primary.md exactly (-9.7 [-13.5, -6.0]). Under the symmetric scorer, the CI excludes 0.

## 2. Every e2e arm

test-v2, 349 cases, 1 rep each.

| arm | n | legacy e2e % [CI] | sym e2e % [CI] | sym − legacy pp | rows changed | sym: 1st call | sym: + clarification | sym: + recovery | sym skill_correct % |
|---|---|---|---|---|---|---|---|---|---|
| E0 native (no router) | 349 | 55.6 [50.1, 60.7] | **56.2 [50.7, 61.3]** | +0.6 | +2 / −0 | 53.6 | 1.7 | 0.9 | 82.2 |
| E1 regex | 349 | 34.7 [29.8, 39.5] | **41.5 [36.4, 46.7]** | +6.9 | +24 / −0 | 40.7 | 0.6 | 0.3 | 62.5 |
| E5 Sonnet 5 | 349 | 50.7 [45.3, 55.9] | **56.2 [50.7, 61.3]** | +5.4 | +19 / −0 | 55.0 | 1.1 | 0.0 | 81.1 |
| E6b Qwen3-8B local | 349 | 46.4 [41.3, 51.6] | **55.0 [49.6, 60.2]** | +8.6 | +30 / −0 | 53.3 | 1.4 | 0.3 | 79.9 |
| E7 regex->Jev | 349 | 45.0 [39.8, 50.1] | **54.2 [48.7, 59.3]** | +9.2 | +32 / −0 | 52.1 | 1.7 | 0.3 | 80.8 |
| E9 regex->Jev->Sonnet | 349 | 45.8 [40.4, 51.0] | **53.0 [47.6, 58.2]** | +7.2 | +25 / −0 | 51.9 | 1.1 | 0.0 | 79.7 |
| E11 hybrid | 349 | 44.4 [39.3, 49.6] | **52.1 [46.7, 57.3]** | +7.7 | +27 / −0 | 50.7 | 1.4 | 0.0 | 76.2 |
| E9 all skill tools (D-002) | 349 | 48.1 [43.0, 53.3] | **55.0 [49.6, 60.2]** | +6.9 | +24 / −0 | 54.4 | 0.6 | 0.0 | 80.8 |
| E7 all skill tools (D-002) | 349 | 44.7 [39.5, 49.9] | **53.0 [47.9, 58.2]** | +8.3 | +29 / −0 | 51.3 | 1.4 | 0.3 | 79.4 |

`rows changed` = turns whose e2e verdict differs between the two scorers: +failure→success / −success→failure. In every arm the symmetric scorer only turns failures into successes, never the reverse.

## 3. Contrasts (paired, unadjusted, EXPLORATORY)

|  | contrast | legacy Δ pp [95% CI] | legacy run-only / ref-only | sym Δ pp [95% CI] | sym run-only / ref-only | sym CI |
|---|---|---|---|---|---|---|
| H3 | E9 − E0 | -9.7 [-13.5, -6.0] | 6 / 40 | -3.2 [-6.0, -0.3] | 7 / 18 | excludes 0 |
|  | E1 − E0 | -20.9 [-25.8, -16.0] | 8 / 81 | -14.6 [-19.2, -10.0] | 10 / 61 | excludes 0 |
|  | E5 − E0 | -4.9 [-8.3, -1.4] | 11 / 28 | 0.0 [-2.6, 2.6] | 11 / 11 | includes 0 |
|  | E6b − E0 | -9.2 [-13.2, -5.2] | 12 / 44 | -1.1 [-4.3, 2.0] | 13 / 17 | includes 0 |
|  | E7 − E0 | -10.6 [-14.6, -6.9] | 8 / 45 | -2.0 [-4.9, 0.9] | 10 / 17 | includes 0 |
|  | E11 − E0 | -11.2 [-15.5, -6.9] | 10 / 49 | -4.0 [-7.4, -0.6] | 11 / 25 | excludes 0 |
| D-002 | E9-full − E0 | -7.4 [-11.5, -3.4] | 13 / 39 | -1.1 [-4.3, 2.0] | 13 / 17 | includes 0 |
| D-002 | E7-full − E0 | -10.9 [-14.9, -6.9] | 8 / 46 | -3.2 [-6.0, -0.3] | 8 / 19 | excludes 0 |
| D-002 | E9-full − E9 | 2.3 [0.0, 4.6] | 12 / 4 | 2.0 [-0.3, 4.3] | 12 / 5 | includes 0 |
| D-002 | E7-full − E7 | -0.3 [-2.3, 2.0] | 7 / 8 | -1.1 [-3.4, 1.1] | 6 / 10 | includes 0 |

## 4. Same calls, different verdict

Discordant cases (e2e success in exactly one of the two runs), and how many of them have the SAME sequence of executed business calls (no `load_skill`) in both runs. Phase 1 reported 22 of the 40 E0-only cases of E9 − E0 as classes A1 + A2 (same calls AND the router's skill label not accepted; `exploratory_e2e.md` §2). The legacy count here is a little larger because it also includes same-calls cases that failed on args or completion. A remaining same-calls discordance under the symmetric scorer comes from the args or the reply (e.g. a clarification), not from the skill label.

| pair | legacy: E0-only with same calls | legacy: all discordant with same calls | sym: E0-only with same calls | sym: all discordant with same calls |
|---|---|---|---|---|
| E9 vs E0 | 24 / 40 | 26 / 46 | 2 / 18 | 4 / 25 |
| E1 vs E0 | 19 / 81 | 24 / 89 | 3 / 61 | 8 / 71 |
| E5 vs E0 | 19 / 28 | 25 / 39 | 2 / 11 | 8 / 22 |
| E6b vs E0 | 26 / 44 | 32 / 56 | 1 / 17 | 7 / 30 |
| E7 vs E0 | 26 / 45 | 31 / 53 | 0 / 17 | 5 / 27 |
| E11 vs E0 | 23 / 49 | 29 / 59 | 1 / 25 | 7 / 36 |
| E9-full vs E0 | 24 / 39 | 30 / 52 | 2 / 17 | 8 / 30 |
| E7-full vs E0 | 23 / 46 | 28 / 54 | 0 / 19 | 5 / 27 |

## 5. Executor variance runs (rep2 on 60 cases)

Same routing decisions (cache), executor resampled. `flips` = cases (of 60) whose e2e verdict differs between rep 1 (main run) and rep 2.

| run | legacy rep2 e2e % | legacy flips | sym rep2 e2e % | sym flips |
|---|---|---|---|---|
| E0 rep2-60 | 53.3 | 3/60 | 55.0 | 3/60 |
| E9 rep2-60 | 43.3 | 1/60 | 50.0 | 2/60 |

## 6. Provenance

Symmetric scorer hash: 5ad0f65296e4. Legacy scorer hash: e0eef1fb0073 (unchanged, asserted by `tests/test_phase1_hashes.py`). Re-score command: `uv run study rescore results/<run>.jsonl --scorer sym`.

| run | rows | raw sha256 | legacy scorer | sym scorer |
|---|---|---|---|---|
| v2-e0-native-e2e-r1 | 349 | 296f62b8eb75 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e1-regex-e2e-r1 | 349 | b97aeba66155 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e5-sonnet-canonical-e2e-r1 | 349 | b1072e852da1 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e6b-qwen-canonical-e2e-r1 | 349 | a4e70bc51a75 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e7-tuned-e2e-r1 | 349 | 6a18ec1afcea | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e9-tuned-e2e-r1 | 349 | d25dc21ced7d | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e11-hybrid-e2e-r1 | 349 | ea59ebcd04a6 | e0eef1fb0073 | 5ad0f65296e4 |
| x-e9-fullskill-e2e-r1 | 349 | 2fec42caaa61 | e0eef1fb0073 | 5ad0f65296e4 |
| x-e7-fullskill-e2e-r1 | 349 | a9242cc6e4f6 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e0-native-e2e-rep2-60 | 60 | 626253131ee1 | e0eef1fb0073 | 5ad0f65296e4 |
| v2-e9-tuned-e2e-rep2-60 | 60 | db4382843c3d | e0eef1fb0073 | 5ad0f65296e4 |

Caveats: post hoc, same test split as the confirmatory analysis, one executor sample per case (the rep2 runs above bound the executor noise). These numbers feed the H1-L effect-size and MDE assumptions of prereg-v2. They are not a phase-1 result.
