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

## Status: PRELIMINARY — selection to be redone (2026-09-30)

A code review found three issues that invalidate part of the selection below. A fix round
follows (`.omc/plans/final-study-master.md`, D6), then the selection will be redone. **No
selection has been applied to `config/experiments`.** The numbers are kept as a record of
the first pass.

1. Bedrock throttling was scored as a wrong answer. Haiku's first subset round ran while
   Sonnet and Jev were running too, and ThrottlingException errors came back as `skill =
   None`: 8, 21 and 12 stage calls under P2k2, P3 and P4. That made those modifiers look
   harmful on Haiku (P3 56.7, P4 68.3, P2k2 71.7) and pruned them. Once the errors were
   retried (`e6_r1_fix`), the same points scored P3 81.7, P4 81.7 and P2k2 80.0, against
   P0 80.0. `tune_router.py` now retries routing errors, which `study run` excludes from
   accuracy, and reports `errors` apart from `parse_fail`.
2. The skill-stage P1 guide renders rules that are false. Clauses are lifted from single
   tools and generalised to the whole skill.
3. The tuner sends `loaded_skill=None` at the tool stage for `__global__`, while the graph
   sends `"__global__"`.

E5b (Qwen3-32B) was dropped from the study by the user (time), in commit 7f674ec. For
reference only, the pre-study `bench_local` gave the 32B skill/tool p50 of 9.4 s / 33.7 s and
joint 85% on 20 dev cases (`.omc/handoffs/providers.md`).

### First-pass results (full dev, 151 cases; CV joint mean ± std over 5 folds)

| model | P0 | P0+P1 | P0+P3 | P0+P6 | P0+P6c | other | first-pass tuned (nested) |
|---|---|---|---|---|---|---|---|
| Sonnet 5 | 78.2 ± 7.5 | 78.8 ± 7.4 | **82.2 ± 7.3** | 79.5 | 79.5 | P2k2 79.5 | P0+P3 (82.2) |
| Haiku 4.5 | 80.8 ± 3.1 | 80.8 ± 3.7 | — ¹ | 80.8 | **81.5 ± 4.9** | | P0+P6c (81.5) |
| Jev | 79.5 ± 10.6 | **80.8 ± 8.1** | 78.9 | 79.5 | 76.9 | P2k2+P6c 80.2, P2k2 78.9 | P0+P1 (78.2) |
| Qwen3-8B | 81.5 ± 6.0 | **83.5 ± 7.5** | 81.5 | 78.8 | 77.5 | P4 82.2, P1+P4 82.2 | P0+P1 (83.5) |
| **mean over the 4** | 80.0 | **81.0** | — | 79.7 | 78.9 | | |

¹ Not run on full dev: first pruned by the throttling artefact, then the Bedrock budget ran
out (a Haiku full-dev pass costs about $0.49; $0.49 was left). The subset estimate, 81.7, would
tie P3 with P1 across the 4 models (about 81.1 vs 81.0).

First-pass canonical: P0+P1, best mean over the candidates run on full dev for every model.
Issue 2 bears directly on that choice.

### Output-format axis (tool stage; full dev)

| model | format | joint | out tok/call | tool p50 ms | case p50 / p95 ms | $/1k cases |
|---|---|---|---|---|---|---|
| Sonnet 5 | verbose (P0) | 78.2 | 157 | 3609 | 6039 / 9461 | 5.64 |
| | scored top-3 (P6) | 79.5 | 81 | 2523 | 4904 / 8243 | 4.04 |
| | compact ids (P6c) | 79.5 | 74 | 2426 | 4813 / 7842 | 3.88 |
| Haiku 4.5 | verbose | 80.8 | 148 | 2313 | 3555 / 6294 | 5.31 |
| | scored | 80.8 | 86 | 1479 | 2736 / 4933 | 4.63 |
| | compact | 81.5 | 63 | 1239 | 2515 / 4483 | 4.32 |
| Jev | verbose | 79.5 | 227 | 2051 | 4017 / 8846 | 0.84 |
| | scored | 79.5 | 151 | 1412 | 3428 / 9811 | 0.88 |
| | compact | 76.9 | 122 | 1575 | 3605 / 9694 | 0.57 |
| Qwen3-8B | verbose | 81.5 | 77 | 8479 | 11105 / 13004 | 0 |
| | scored | 78.8 | 51 | 5666 | 8253 / 9545 | 0 |
| | compact | 77.5 | 27 | 3874 | 6500 / 7718 | 0 |

- Output tokens are per call, averaged over the skill and tool stages.
- Compact ranking cuts the tool-stage p50 by 23–54% and the output tokens by 46–65%.
  - On the Bedrock models it costs no accuracy (+0.7 and +1.3 points) and is 19–31% cheaper.
  - It costs the 8B 4.0 points and Jev 2.6 points. The cause was not investigated.

### Context economics (full dev, per routing call)

| model | variant | prompt tok (static / dyn) | cache read / write | $/1k |
|---|---|---|---|---|
| Sonnet 5 | P0 | 2225 (2106 / 119) | 1816 / 136 | 5.64 |
| Sonnet 5 | P0+P1 | 2730 (2636 / 94) | 2304 / 153 | 5.82 |
| Haiku 4.5 | P0 | 1916 (1825 / 90) | 0 / 0 (prefix < 4096) | 5.31 |
| Haiku 4.5 | P0+P1 | 2303 (2224 / 80) | 0 / 0 | 6.06 |
| Jev | P0 / P0+P1 | 1150 / 1505 | 0 / 0 | 0.84 / 0.96 |
| Qwen3-8B | P0 / P0+P1 | 954 / 1278 | n/a (KV prefix reuse) | 0 |

- Sonnet 5 reads about 82–84% of its prompt from cache. P1 adds about 500 static tokens but
  costs only +3%, because those tokens are cached reads at $0.20/M.
- Haiku 4.5 never reaches its 4096-token cache minimum, so the same guide costs it +14%.
  Output tokens dominate Sonnet's bill: $10/M against $0.20/M for a cached read.

### Confidence (first pass)

- Isotonic maps were fitted on dev folds (`--calibrate`). On held-out folds they lower ECE
  for most model/stage pairs. Examples: Haiku P6c goes from 0.039/0.057 to 0.021/0.050, and
  the 8B P1 tool stage from 0.112 to 0.059.
- Sonnet P3 at the tool stage is the exception: 0.100 → 0.111. The maps are small (151 cases).
- The 8B self-reports only 0.95 or 1.0.
- Logprob confidence (json_object mode, P0+P1, full dev) was compared on the 8B:
  - joint 82.8 against 83.5 with the grammar;
  - raw ECE 0.066/0.157 against 0.028/0.112;
  - calibrated tool ECE 0.047 against 0.059;
  - p95 28.9 s against 13.7 s.
  It does not pay off, so the plan keeps `self_reported`.

### Spend of the first pass

- Bedrock: $9.64 of the $10 allowance. The ledger went from $0.1304 to $9.6432, with the cap
  set at $10.13.
- OpenRouter: $0.95 of the $2 allowance. The ledger went from $0.0086 to $0.9555, with the cap
  set at $2.0086.
- Qwen3-8B: $0 (local).

Per-point metrics for every run are in `docs/results/prompt-apex-metrics.json`.

## How to reproduce

```bash
# one model, a list of variants: 60-case stratified subset first (early pruning)
uv run python scripts/analysis/tune_router.py config/experiments/e6b_llm_qwen3_local.yaml \
    --prompt-variant "P0,P0+P6c,P0+P6,P0+P1" --subset 60 --concurrency 1 --preload \
    --out results/prompt_apex/e6b_r1.json
# the survivors on all of dev: same command without --subset (the subset cases are cached);
# add --calibrate to print the isotonic maps of the best point
uv run python scripts/analysis/prompt_apex_report.py results/prompt_apex/*.json   # tables
uv run python scripts/analysis/apply_prompt_selection.py   # config/prompt_selection.yaml -> configs
```

- Paid runs need the budget caps in the environment, for example
  `BUDGET__AWS_USD_CAP=10.13 BUDGET__OPENROUTER_USD_CAP=2.0086` (the ledger's spend before
  the study plus US$ 10 and US$ 2). For Jev, add `--set strategies.jev.cache=true` so no
  decision is paid for twice.
- Local runs use `--concurrency 1 --preload`, with one resident model and `num_ctx` 8192.
- Everything is served from `.cache/responses` after the first pass. Re-running the tables or
  the calibration costs nothing.

## Method

**Data.** Only `data/dataset_dev.jsonl` (151 cases) is read. The test split was never opened.
Few-shot messages come from the MCP catalog (`_meta.examples` of each tool); none come from
the dataset.

**Protocol.** 5-fold cross-validation, stratified by category, with seed 0. A router has no
state fitted on data, so every variant is scored once on every dev case and then summarised
per fold:

- "CV joint" is the mean ± std over the 5 folds of the fixed variant;
- "nested" is the honest estimate of the selection itself: in each fold, pick the best
  variant on the other 4 folds and score it on the held-out fold;
- ties go to the lower cost per 1k cases, then to the lower p50.

**Search (greedy, with early pruning).**

1. Round 1 scores P0 and every single modifier on top of P0 on a stratified 60-case subset
   (`--subset 60`, seed 0).
2. Round 2 combines the modifiers that helped a model, still on the subset.
3. The survivors go to the full dev split. The subset cases are cached, so only the other
   91 cases are paid for.

On the subset one case is 1.7 points (0.66 on full dev) and the fold std is 6–19 points, so a modifier is dropped
only when it clearly hurts, never for a one-case difference.

**Same inputs for every router:**

- option text from the catalog (catalog hash `785db6efc779`);
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
