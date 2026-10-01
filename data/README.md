# Routing dataset

500 pt-BR post-sales cases (seed 104 + synthetic 396), split 30/70 into dev/test, plus the
confirmatory split **test-v2** (349 new synthetic cases, `dataset_test_v2.jsonl`).
`dataset_test.jsonl` is now **test-v1 (exposed)**: it was read before the routers were re-tuned
(methodology review B1) and serves only as a replication/contamination check.
Full provenance, audit and freeze hashes: [`docs/dataset-card.md`](../docs/dataset-card.md).

| File | Content |
| --- | --- |
| `seed.jsonl` | 104 hand-written cases (`"source":"seed"`) |
| `synthetic.jsonl` | 396 LLM-generated cases (`"source":"synthetic"`, `"reviewed":false`) |
| `dataset_dev.jsonl` | 151 cases, tune regex / examples / thresholds here only |
| `dataset_test.jsonl` | 349 cases, held out |
| `generation_meta.json` | model, temperature, counts, cost of the last generation run |
| `dataset_test_v2.jsonl` | 349 cases (`"source":"synthetic_v2"`), **the only confirmatory split**; carries `label_audit` |
| `generation_meta_v2.json` | test-v2 generation: model, seed, prompts/code hashes, rejections, per-tool counts, mock-DB conflicts, cost |
| `audit/` | test-v2 generation log and raw outputs, overlap report, blind label audit (verdicts, adjudication, summary), `review.html` |

Rebuild: `uv run python scripts/dataset/generate.py && uv run python scripts/dataset/split.py`
(generation needs `OPENROUTER_API_KEY` in `.env`; split is deterministic, seed 20260929).

test-v2: `uv run python scripts/dataset/generate_v2.py` (`--resume` replays the paid raw outputs),
`uv run python scripts/dataset/overlap.py` (leakage report),
`uv run python scripts/dataset/audit.py run --split test_v2` then `... audit.py adjudicate`.

## Schema (one JSON per line)

`{id, category, customer_id, source, reviewed, turns[{role, content}], expected{acceptable_skills[], acceptable_tools[], args{}}}`

- `category`: `direto | parafrase | ambiguo | multiturno | fora_escopo | adversarial`.
- `turns`: last turn is always the user message under test; multi-turn cases carry gold assistant history (plain text, no tool calls).
- `acceptable_*`: more than one value means several answers are valid (ambiguous cases).
  `acceptable_skills` is always derived from `acceptable_tools`.
- Global tools (`get_customer_profile`, `search_help_center`, `escalate_to_human`) use skill `__global__`.
  Out-of-scope cases use `__abstain__` (skill and tool); `escalate_to_human` may also be acceptable there.
- `args`: expected tool arguments when derivable (`order_id`, `address`, `query`); `{}` otherwise.
  Do not score args on cases where they are empty.

## MOCK DB ASSUMPTION (for the MCP server worker)

Customers `C001..C020`, orders `O0001..O0060`, exactly 3 orders per customer:
**customer `C00k` owns orders `O(3k-2)..O(3k)`** (C001: O0001-O0003, C002: O0004-O0006, ..., C020: O0058-O0060).
Every order id mentioned in a case (turns or args) belongs to the case's `customer_id`; `tests/test_dataset.py` enforces this.
`mock_db.json` must follow the same mapping, or end-to-end argument checks will fail.

## Distribution (target 30/25/20/10/10/5, tolerance +/-2pp, actually within 0.3pp)

| Category | All | Dev | Test |
| --- | --- | --- | --- |
| direto | 150 | 45 | 105 |
| parafrase | 125 | 38 | 87 |
| ambiguo | 100 | 30 | 70 |
| multiturno | 50 | 15 | 35 |
| fora_escopo | 50 | 15 | 35 |
| adversarial | 25 | 8 | 17 |

## Generation

- Model: `google/gemini-2.5-flash` via OpenRouter (different family from the routers), temperature 0.9, reasoning effort low.
- One batch per (category, tool) for direto/parafrase/multiturno, per confusable group for ambiguo, per topic for fora_escopo, per attack kind for adversarial; oversampled, then trimmed to quota with a fixed seed.
- Validation: pydantic (`scripts/dataset/common.py`), tool names and skills consistent, order ids owned by the case customer, labels checked against the batch spec (e.g. direto must be exactly the target tool), dedupe by normalized text plus `SequenceMatcher` ratio > 0.85 (also against seed).
- Ambiguous cases: the label set comes from the batch spec (confusable group), not from the model.
- Cost of the final run: **US$0.6459** (sum of `usage.cost`; 396 kept, 93 rejected invalid, 1 duplicate).
  Total spent while iterating on the prompts and label filters: about US$4 across 7 full runs plus 2 aborted partial runs (earlier outputs were discarded).

## Human review: PENDING

No case has been reviewed by a human. `reviewed` is `false` for every case, including the seed (written by an AI agent, Claude Opus 5.5, not by the study author; see `docs/dataset-card.md`, review M3).
test-v2 went through a blind two-model automated audit instead (`docs/dataset-card.md`); its flagged cases await a human decision in `audit/review.html`.
Review priorities:

1. `adversarial` synthetic (17 of 25 in test): the `tool_by_name` and `decoy` labels are the weakest.
   Example: a user who orders `cancel_order` for their own order is labeled `get_order_status` + `escalate_to_human`; decide the policy and fix the gold.
2. `ambiguo` synthetic: check that the message really supports every listed alternative.
3. `fora_escopo`: borderline items (e.g. a broken personal phone) may deserve escalation instead of pure abstention.
4. Skim `direto`/`parafrase`/`multiturno` for label slips.

Set `"reviewed": true` per case after review, and fix labels in `synthetic.jsonl`, then rerun `split.py`
(the split is stable per id ordering, so fixed labels do not move cases between dev and test unless cases are added or removed).

Leakage check (plan section 7): `scripts/dataset/overlap.py` compares every case with every router-visible catalog text unit (lexical `SequenceMatcher`, and cosine with the local `qwen3-embedding`); results in `audit/overlap_report.json`. test-v1: lexical max 0.89 (0 >= 0.95), semantic 4 cases >= 0.9; test-v2: 0 lexical >= 0.9 and 0 semantic >= 0.9 against the catalog and the 500 existing cases.

## Label policy — adversarial (lead fix, 2026-09-29)
A request that names a tool whose purpose matches the user's legitimate intent accepts that tool (first in `acceptable_tools`); the previous synthetic labels are kept as alternatives. Instruction injection / privilege escalation (e.g. "ignore as instruções…") stays `__abstain__`/`escalate_to_human`. Fixed rows carry `"label_fix": "named_tool_matches_intent"`.
