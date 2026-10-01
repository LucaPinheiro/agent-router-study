# Router prompt study: canonical track (A) and per-model tuned track (B)

Plan: `.omc/plans/prompt-apex.md` (user decision 2026-09-30). Every LLM-type router is scored
with one shared prompt (the **canonical** track) and with its own best prompt (the **tuned**
track). Both prompts were chosen on the dev split. The canonical track is the study's main
table: with the prompt held fixed, a difference between routers comes from the model. The
tuned track shows each router's ceiling and how much prompt engineering adds per model.

| router | experiment | model | where it runs |
|---|---|---|---|
| llm (Sonnet 5) | E5 | `global.anthropic.claude-sonnet-5` | Bedrock |
| llm (Haiku 4.5) | E6 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock |
| llm_local (Qwen3-8B) | E6b | `qwen3:8b-q8_0` (num_ctx 8192) | Ollama |
| jev | E4 | `typesafe/jev-router` | OpenRouter |

## Status: D6 selection redone on the fixed code (2026-10-01): Sonnet 5, Haiku 4.5, Jev

The selection is in `config/prompt_selection.yaml`, written by
`scripts/analysis/select_prompts.py`. The lead applies it with `apply_prompt_selection.py`;
`config/experiments` has not been edited. Qwen3-8B (E6b) is not in this pass: the lead runs it
later with the same procedure (see "Adding Qwen3-8B") and recomputes the canonical choice.

**Why the first pass was thrown away.** Three bugs biased it, so none of its numbers are reused:

- Bedrock throttling errors were scored as abstentions, which pruned Haiku's P2k2, P3 and P4.
- The P1 skill guide rendered rules that are false (fixed in 3c9e261).
- The tuner sent `loaded_skill=None` on `__global__` (fixed in 69209dd).

The catalog text also changed (F8 and F10, catalog hash `785db6efc779` → `33f89f3db4f5`). That
changed every prompt, so every decision was paid for again.

### Result: P0 on both tracks for all three models

| model | canonical | tuned | nested-CV joint (tuned) | raw best on full dev (not selected) |
|---|---|---|---|---|
| Sonnet 5 | P0 | P0 | 77.5 ± 9.8 | P0+P4 80.2 (5 cases gained, 1 lost vs P0) |
| Haiku 4.5 | P0 | P0 | 81.5 ± 3.8 | P0+P4 83.5 (3 gained, 2 lost) |
| Jev | P0 | P0 | 78.2 ± 9.4 | P0+P5 80.9 (8/4); P0+P6c 80.9 (6/2) |

- **No modifier beats P0 by more than one standard error** (5 folds × 151 cases). The one-SE
  rule therefore keeps the simplest prompt every time.
  - The SE of the best variant is 2.2–6.2 points: Haiku 2.2, Sonnet 3.7, Jev 6.2 (P5).
  - The largest full-dev gain is +2.7 points (Sonnet with P4). It comes from 6 discordant
    cases, 5 to 1, so an exact sign test gives p ≈ 0.22.
- **Canonical track.** The candidates are the variants run on full dev for every model: P0, P4
  and P5. Their mean CV joint over the three models is P0 79.5, P0+P4 80.2 and P0+P5 79.5. P0 is
  inside one SE and is the simplest, and each outer fold of the nested CV picks P0 too.
- **The tuned track equals the canonical track for all three models.** With this rule, prompt
  engineering adds nothing measurable on 151 cases. That is the finding for RQ "tuned vs
  canonical".
- **Sensitivity: plain argmax instead of the one-SE rule** (nested CV, best mean per fold):

  | model | nested-CV joint | picks |
  |---|---|---|
  | Sonnet | 80.2 ± 7.5 | P4 in all 5 folds |
  | Haiku | 82.2 ± 3.2 | P4 in 4 folds |
  | Jev | 78.9 ± 10.4 | P5 and P6c |

  If the lead prefers the higher-variance argmax rule, the tuned track would be Sonnet P0+P4
  and Haiku P0+P4. The YAML records `raw_best` for this.
- **Jev cost.** P0+P6c (compact ranking) costs 35% less than P0 ($0.60 against $0.93 per 1k
  cases), cuts p50 by 20% (4.0 s against 5.0 s) and p95 by 35%, at equal or better accuracy
  (80.9 against 78.2). It is not selected, because it adds a modifier and the gain is within
  one SE. It is the cheapest choice to keep in mind for an E4/E7 cost variant.

### Per model × track (full dev, 151 cases; selection as written to the YAML)

The columns:

- nested-CV joint: the selection procedure, run inside the CV;
- fixed CV joint: the chosen variant alone;
- ECE: cross-fitted, with the map fitted on 4 folds and applied to the held-out fold;
- $/1k: the routing cost per 1000 cases (skill + tool call);
- static and cache-read tokens: per routing call.

| model | track | variant | nested-CV joint | fixed CV joint | ECE skill raw→cal | ECE tool raw→cal | $/1k | p50 / p95 ms | static tok | cache-read tok | err % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Sonnet 5 | canonical | P0 | 77.5 ± 9.8 | 77.5 ± 9.8 | 0.111→0.091 | 0.036→0.056 | 5.97 | 5640 / 9403 | 2119 | 1746 | 0.0 |
| Sonnet 5 | tuned | P0 | 77.5 ± 9.8 | 77.5 ± 9.8 | 0.111→0.091 | 0.036→0.056 | 5.97 | 5640 / 9403 | 2119 | 1746 | 0.0 |
| Haiku 4.5 | canonical | P0 | 82.8 ± 3.3 | 82.8 ± 3.3 | 0.058→0.063 | 0.055→0.061 | 5.32 | 3319 / 5066 | 1826 | 0 | 0.0 |
| Haiku 4.5 | tuned | P0 | 81.5 ± 3.8 | 82.8 ± 3.3 | 0.058→0.063 | 0.055→0.061 | 5.32 | 3319 / 5066 | 1826 | 0 | 0.0 |
| Jev | canonical | P0 | 78.2 ± 9.4 | 78.2 ± 9.4 | 0.063→0.024 | 0.047→0.058 | 0.93 | 5006 / 12455 | 1107 | 784 | 0.7 |
| Jev | tuned | P0 | 78.2 ± 9.4 | 78.2 ± 9.4 | 0.063→0.024 | 0.047→0.058 | 0.93 | 5006 / 12455 | 1107 | 784 | 0.7 |

- **Calibration.** Isotonic maps per stage are fitted on all of dev and written to the YAML.
  Cross-fitted, they help only in some cases:
  - they help Sonnet's skill stage (0.111 → 0.091) and Jev's skill stage (0.063 → 0.024);
  - they slightly hurt Sonnet's tool stage (0.036 → 0.056), Haiku (0.058/0.055 → 0.063/0.061)
    and Jev's tool stage (0.047 → 0.058). Those raw confidences are already well calibrated, and
    151 cases are too few for the map.

  The lead decides whether to apply a map to a stage where it hurts. The YAML has `ece_raw` and
  `ece_cal` per stage.
- Errors (ITT): at most 1 failed row per full-dev point (0.7%), all of them parse failures that
  persisted after the retries. One variant had more than 2% failed rows: Jev P0 on the subset
  (2 of 60). Every Jev and Sonnet grid with a failure was re-run before scoring. The response
  cache serves the successes, so only the failures were paid for again. Each run's first pass is kept
  as `*_pass1.json`.

### Search log (what was run, and on which cases)

The procedure for each model:

1. Round 1 ran on a stratified 60-case subset with seed 0. It scored P0 and every single
   modifier: P1, P2k2, P3, P4, P5, P6 and P6c.
   - Bedrock first ran P0, P6c, P1, P2k2, P3 and P4.
   - P6 and P5 were added afterwards, when the budget allowed. Their verdicts are on the same
     subset.
2. Pruning used only the cases that are error-free for every variant of the round. A variant
   was dropped only when its paired joint difference to the subset leader was below −1 SE,
   where SE = sd(per-case difference)/√n. P0 is never dropped.
3. Round 2 combined the modifiers that survived. Only Jev had more than one, and it ran
   P6c+P5 and P6c+P2k2.
4. The survivors went to full dev, where only the remaining 91 cases are new.
5. Canonical candidates are the variants that survived on at least 2 of the 3 models: P0, P4
   and P5. They were run on full dev for every model, including Jev P4, which was pruned on
   Jev's own subset.
6. Budget-truncated: Haiku P6 survived its subset but was not run on full dev, because the
   Bedrock budget was spent. On the subset it was 80.0 against 83.3 for P0, 1 gained and 3 lost.

"b+/c−" counts the discordant cases against P0: the variant right and P0 wrong, then the
reverse.

### Full-dev variants per model (fixed-point CV joint; discordant vs P0 = (+, −))

| model | variant | CV joint | b+/c− vs P0 | $/1k | p50 ms | out tok | err % |
|---|---|---|---|---|---|---|---|
| Sonnet 5 | P0 | 77.5 ± 9.8 | 0/0 | 5.97 | 5640 | 157 | 0.0 |
| Sonnet 5 | P0+P4 | 80.2 ± 7.5 | 5/1 | 6.46 | 6126 | 195 | 0.0 |
| Sonnet 5 | P0+P5 | 76.9 ± 7.4 | 4/5 | 5.34 | 5733 | 156 | 0.7 |
| Haiku 4.5 | P0 | 82.8 ± 3.3 | 0/0 | 5.32 | 3319 | 148 | 0.0 |
| Haiku 4.5 | P0+P4 | 83.5 ± 4.5 | 3/2 | 5.70 | 3793 | 175 | 0.0 |
| Haiku 4.5 | P0+P5 | 80.8 ± 5.2 | 1/4 | 5.40 | 3389 | 148 | 0.0 |
| Jev | P0 | 78.2 ± 9.4 | 0/0 | 0.93 | 5006 | 225 | 0.7 |
| Jev | P0+P6c | 80.9 ± 9.6 | 6/2 | 0.60 | 4010 | 118 | 0.0 |
| Jev | P0+P4 | 76.9 ± 9.7 | 5/7 | 0.83 | 5336 | 223 | 0.7 |
| Jev | P0+P1 | 78.9 ± 11.9 | 3/2 | 0.96 | 5370 | 230 | 0.0 |
| Jev | P0+P2k2 | 80.1 ± 8.9 | 5/2 | 0.91 | 4823 | 209 | 0.0 |
| Jev | P0+P5 | 80.9 ± 12.5 | 8/4 | 0.77 | 5498 | 230 | 0.0 |
| Jev | P0+P6c+P5 | 78.9 ± 11.6 | 7/6 | 0.50 | 4429 | 116 | 0.0 |

### Subset pruning (60 cases, error-free for all variants)

| model | variant | joint | Δ vs leader | SE | pruned | b+/c− vs P0 | errors |
|---|---|---|---|---|---|---|---|
| Sonnet 5 | P0 | 79.7 | -5.1 | 2.9 | no | -/- | 0 |
| Sonnet 5 | P0+P6c | 81.4 | -3.4 | 2.4 | yes | 2/1 | 0 |
| Sonnet 5 | P0+P1 | 79.7 | -5.1 | 2.9 | yes | 2/2 | 0 |
| Sonnet 5 | P0+P2k2 | 78.0 | -6.8 | 3.3 | yes | 1/2 | 0 |
| Sonnet 5 | P0+P3 | 79.7 | -5.1 | 2.9 | yes | 1/1 | 0 |
| Sonnet 5 | P0+P4 | 84.8 | 0.0 | 0.0 | no | 3/0 | 0 |
| Sonnet 5 | P0+P6 | 81.4 | -3.4 | 2.4 | yes | 2/1 | 0 |
| Sonnet 5 | P0+P5 | 83.0 | -1.7 | 1.7 | no | 3/1 | 1 |
| Haiku 4.5 | P0 | 83.3 | 0.0 | 0.0 | no | -/- | 0 |
| Haiku 4.5 | P0+P6c | 78.3 | -5.0 | 3.7 | yes | 1/4 | 0 |
| Haiku 4.5 | P0+P1 | 78.3 | -5.0 | 2.8 | yes | 0/3 | 0 |
| Haiku 4.5 | P0+P2k2 | 80.0 | -3.3 | 2.3 | yes | 0/2 | 0 |
| Haiku 4.5 | P0+P3 | 80.0 | -3.3 | 2.3 | yes | 0/2 | 0 |
| Haiku 4.5 | P0+P4 | 83.3 | 0.0 | 2.4 | no | 1/1 | 0 |
| Haiku 4.5 | P0+P6 | 80.0 | -3.3 | 3.3 | no | 1/3 | 0 |
| Haiku 4.5 | P0+P5 | 81.7 | -1.7 | 2.9 | no | 1/2 | 0 |
| Jev | P0 | 79.7 | -5.1 | 3.8 | no | -/- | 0 |
| Jev | P0+P6c | 84.8 | 0.0 | 0.0 | no | 5/1 | 0 |
| Jev | P0+P6 | 79.7 | -5.1 | 3.8 | yes | 1/0 | 0 |
| Jev | P0+P1 | 81.4 | -3.4 | 3.4 | no | 1/0 | 0 |
| Jev | P0+P2k2 | 81.4 | -3.4 | 4.2 | no | 2/1 | 0 |
| Jev | P0+P3 | 76.3 | -8.5 | 4.4 | yes | 2/3 | 0 |
| Jev | P0+P4 | 78.0 | -6.8 | 3.3 | yes | 1/2 | 1 |
| Jev | P0+P5 | 81.4 | -3.4 | 3.4 | no | 3/1 | 0 |
| Jev | P0+P6c+P5 | 81.0 | -3.5 | 3.5 | no | 2/1 | 1 |
| Jev | P0+P6c+P2k2 | 77.6 | -6.9 | 4.2 | yes | 1/2 | 0 |

Canonical over Sonnet 5, Haiku 4.5, Jev: **P0** (raw best P0+P4); mean CV joint per candidate: P0 79.5, P0+P4 80.2, P0+P5 79.5; nested mean 79.5 (picks P0, P0, P0, P0, P0).

### Output format and context economics (per routing call)

| model | variant | n | prompt tok (static / dyn) | cache read / write | out tok | $/1k | case p50 / p95 ms | tool p50 ms |
|---|---|---|---|---|---|---|---|---|
| Sonnet 5 | P0 | 151 | 2229 (2119 / 111) | 1746 / 209 | 157 | 5.97 | 5640 / 9403 | 3481 |
| Sonnet 5 | P0+P4 | 151 | 2302 (2196 / 106) | 1887 / 141 | 195 | 6.46 | 6126 / 8602 | 3658 |
| Sonnet 5 | P0+P6c | 60 | 2148 (2041 / 108) | 1697 / 172 | 75 | 4.15 | 4526 / 6417 | 2292 |
| Haiku 4.5 | P0 | 151 | 1917 (1826 / 92) | 0 / 0 | 148 | 5.32 | 3319 / 5066 | 2177 |
| Haiku 4.5 | P0+P4 | 151 | 1978 (1886 / 92) | 0 / 0 | 175 | 5.70 | 3793 / 5311 | 2417 |
| Haiku 4.5 | P0+P6c | 60 | 1855 (1760 / 94) | 0 / 0 | 64 | 4.35 | 2483 / 3827 | 1329 |
| Jev | P0 | 151 | 1157 (1107 / 50) | 784 / 31 | 225 | 0.93 | 5006 / 12455 | 2932 |
| Jev | P0+P6c | 151 | 1043 (997 / 46) | 676 / 40 | 118 | 0.60 | 4010 / 8143 | 1721 |
| Jev | P0+P1 | 151 | 1460 (1409 / 51) | 1019 / 36 | 230 | 0.96 | 5370 / 11116 | 2913 |

- **Output tokens dominate the bill.** Compact ranking (P6c) halves the output tokens, cuts
  cost by 18–38% and cuts tool-stage p50 by 33–41%.
  - On the Bedrock subsets it still lost accuracy against the leader. Haiku P0+P6c went 1
    gained and 4 lost against P0, so it was pruned.
- **P4 (rationale) costs +7–8% ($) and +9–14% p50** for its +0.7 to +2.7 points.
- **Caching.**
  - Sonnet 5 reads about 78–82% of its prompt from cache.
  - Haiku 4.5 never reaches its 4096-token cache minimum.
  - Jev's upstream (OpenRouter) now reports cache reads of about 68% of its prompt.
  - P1 adds about 300–400 static tokens per call. On Sonnet they are cached reads.

### Spend of this pass (ledger deltas)

- **Bedrock: $7.93 of the $8 allowance.** The ledger went from $9.658 to $17.589, with
  `BUDGET__AWS_USD_CAP=17.658`.
  - Subset rounds cost about $4.9 (8 variants × 2 models).
  - Full dev cost about $3.0 (P0, P4 and P5 × 2 models, 91 new cases each).
- **OpenRouter (Jev only): $0.92 of the $1 allowance.** The `typesafe/jev-router` line went
  from $0.9555 to $1.8774.
  - Other workers spent on OpenRouter at the same time, so the env cap was reset before each
    launch to their current total plus the Jev allowance still left.
- Response cache: every successful decision is in `.cache/responses`, so re-running any
  command below is free.

### Adding Qwen3-8B (lead), and recomputing the canonical choice

```bash
C=config/experiments/e6b_llm_qwen3_local.yaml; O=results/prompt_apex_v2
uv run python scripts/analysis/tune_router.py $C --concurrency 1 --preload --subset 60 \
    --prompt-variant "P0,P0+P6c,P0+P1,P0+P2k2,P0+P3,P0+P4,P0+P6,P0+P5" --out $O/e6b_r1.json
# prune (rule above; select_prompts.py prints the verdicts), then full dev for the survivors
# AND for the canonical candidates P0, P0+P4, P0+P5:
uv run python scripts/analysis/tune_router.py $C --concurrency 1 --preload \
    --prompt-variant "P0,P0+P4,P0+P5,<survivors>" --out $O/e6b_full.json
uv run python scripts/analysis/select_prompts.py --md docs/results/prompt-selection.md \
    --runs "Sonnet 5=global.anthropic.claude-sonnet-5" $O/e5_r1.json $O/e5_full.json $O/e5_full_p5.json \
    --runs "Haiku 4.5=global.anthropic.claude-haiku-4-5-20251001-v1:0" $O/e6_r1.json $O/e6_full.json $O/e6_full_p5.json \
    --runs "Jev=typesafe/jev-router" $O/e4_r1.json $O/e4_r2.json $O/e4_full.json $O/e4_full_r2.json \
    --runs "Qwen3-8B=qwen3:8b-q8_0" $O/e6b_r1.json $O/e6b_full.json
```

The canonical choice is recomputed over the variants run on full dev for every model given.
If Qwen's survivors add a variant that two models kept, run it on full dev for the other
models too (Jev is cheap; Bedrock needs budget), or leave it out of the canonical candidates
and say so.

## How to reproduce

```bash
source results/prompt_apex_v2/env.sh   # caps: ledger spend at start + 8 (AWS) / + 1 (OpenRouter)
# round 1 on the 60-case subset (Jev: add --set strategies.jev.cache=true)
uv run python scripts/analysis/tune_router.py config/experiments/e5_llm_sonnet.yaml \
    --prompt-variant "P0,P0+P6c,P0+P1,P0+P2k2,P0+P3,P0+P4,P0+P6,P0+P5" --subset 60 \
    --out results/prompt_apex_v2/e5_r1.json
# survivors + canonical candidates on full dev (subset cases come from the cache)
uv run python scripts/analysis/tune_router.py config/experiments/e5_llm_sonnet.yaml \
    --prompt-variant "P0,P0+P4" --out results/prompt_apex_v2/e5_full.json
# selection + calibration + tables (free); then the lead applies it to the configs
uv run python scripts/analysis/select_prompts.py --runs ... (see above)
uv run python scripts/analysis/apply_prompt_selection.py
```

Re-running a command retries only the failed rows; the successes come from the cache. Bedrock
runs are sequential: Sonnet first, then Haiku. Jev ran alongside them, because it is a
different provider.

## Method

**Data.** Only `data/dataset_dev.jsonl` (151 cases) is read. The test split was never opened.
Few-shot messages come from the MCP catalog (`_meta.examples` of each tool); none come from
the dataset.

**Protocol.** 5-fold cross-validation, stratified by category, with seed 0. A router has no
state fitted on data, so every variant is scored once on every dev case and then summarised
per fold. A failed stage is an error and is scored wrong (ITT).

- "Fixed CV joint" is the mean ± std over the 5 folds of one variant.
- The **one-SE rule** picks among the variants:
  1. best = the highest mean;
  2. candidates = every variant with a mean of at least best − SE(best), where SE is the fold
     sd/√5;
  3. among the candidates, the fewest modifier tokens, then the lowest $/1k, then P0. A tie
     goes to P0.
- The **tuned** track applies the rule per model.
- The **canonical** track applies it to the per-fold mean over models, among the variants run
  on full dev for every model.
- "Nested-CV joint" is the honest estimate of the procedure: run the rule on 4 folds and score
  its pick on the held-out fold.

**Same inputs for every router:**

- option text from the catalog (catalog hash `33f89f3db4f5`);
- a history window of 4 turns;
- `max_tokens` 512;
- reasoning off (Qwen thinking off via `reasoning_effort: none`);
- `allow_abstain: false`, so out-of-scope requests go to `__global__` → `escalate_to_human`,
  which the scorer accepts for an `__abstain__` gold (see `route_scores`).

Documented asymmetries:

- Sonnet 5 on Bedrock takes no `temperature`. Haiku and Qwen run at 0.
- Bedrock uses forced tool use. Ollama uses a strict json_schema grammar.
- Jev takes no structured output and no parameters. It gets the same prompt plus the reply
  shape spelled out as plain JSON, and a tolerant parser with one corrective retry.
- Jev is non-deterministic. Its tuning decisions were cached (`cache: true` in the harness
  only), so every variant is one sample.

## Variant space

A variant is a config value, `prompt_variant: "P0+P3"`: tokens joined by `+` and applied left
to right. The templates live in `src/routing_study/prompts/routers/`:

- `variants.yaml` maps each token to its switches;
- `en.yaml` holds the English text; `pt.yaml` the pt-BR text (P5).

`TEMPLATE_HASH` covers the three files and is part of the run's `prompt_hash`. The variant
string is part of `config_hash`.

| token | what it changes |
|---|---|
| P0 | Base: rules → `<options>` (id, description, up to 5 catalog examples) → `<loaded_skill>` / `<history>` / `<message>`. Structured output with an `enum` of ids. Confidence = "probability that the choice is correct". Tool stage: choice + confidence + every other option ranked with its confidence. **P0 is the pre-study prompt, byte for byte** (a test pins this), so older P0 decisions stay valid. |
| P1 | `<guide>`: the catalog's DON'T USE FOR clauses, verbatim, as "not X: situation (use Y)". Only clauses whose target is in the current option set are kept. At the skill stage the tool targets are rewritten as skills and same-skill clauses are dropped. |
| P2k1 / P2k2 | `<examples>`: k catalog messages per option as resolved demonstrations (`"message" -> id`), round-robin over the options. They are taken out of the inline example lists, so nothing is shown twice. The skill stage draws on the skill's tool examples, which gives it new text. |
| P3 | Explicit scope rules. Skill: what `__global__` covers (a person, policy questions without an order, own profile, topics outside the domains), and a vague request about an order goes to its domain. Tool: prefer the specific action or lookup tool, and use the general-purpose ones only when no specific tool fits. |
| P4 | A `rationale` field (at most 15 words) before the decision. Its tokens count in cost and latency. |
| P5 | Instructions in pt-BR (the option text is pt-BR anyway). |
| P6 | Tool stage: `ranking: [{id, score}]`, top 3, best first. Choice = first id; confidence = its score. |
| P6c | Tool stage, compact: `ranking: [id, id, id]` + one `confidence` for the first id (ids only; the alternatives get 0.0). |
| k2 | Top-2 instead of top-3 for P6 / P6c. |

The skill stage always answers `{choice, confidence}`, plus `rationale` under P4. The output
formats apply only to the tool stage: that is the stage the host exposes as top-k, and the
stage where local latency is dominated by output length. The static prefix (rules, options,
guide, examples) is the whole system message. It is sent as a Bedrock `cachePoint`, and Ollama
reuses it through its KV prefix cache.

## Context economics (how to read the columns)

- `prompt` is the mean prompt tokens per routing call, as the provider reports them.
- `static` / `dyn` split that total by the rendered characters of the system prefix versus the
  user message. It is an estimate, because providers report a single total.
- `cache r/w` is the mean cache-read / cache-write tokens per call:
  - Sonnet 5 caches the ~2k-token prefix and reads about 85% of the prompt from cache;
  - Haiku 4.5 needs 4096 tokens before a cache point takes effect, and no variant reaches it;
  - Ollama does not report its prefix reuse.
- `out` is the mean output tokens per call.
- `$/1k` is the routing cost per 1000 cases (skill + tool call). It uses the original cost even
  when the decision came from the cache.
- `p50 / p95` is the case latency (skill + tool). `tool p50` is the tool-stage call alone.
- ECE uses 10 bins, over raw confidence, on the decisions that were made.
