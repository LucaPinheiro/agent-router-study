# RQ5 — maintenance cost of adding a tool (leave-tools-out design)

Answers RQ5 / the "Esforço" metric of `docs/projeto.md` ("linhas de config e horas para
adicionar uma tool nova") and closes methodology review M2 (`.omc/reviews/methodology-final.md`).
Plan item: D7 of `.omc/plans/final-study-master.md`. Status: **exploratory** (not one of the
pre-registered hypotheses H1–H3 / S1–S4 unless promoted at pre-registration).

## Held-out tools

One per skill, including the most confusable pair member:

| Tool | Skill | Why | dev cases | test-v2 cases |
| --- | --- | --- | --- | --- |
| `get_refund_status` | pagamentos_reembolsos | confusable with `request_refund` / `get_payment_status` (same vocabulary: reembolso, estorno, caiu) | 9 (6 multi-label with `get_payment_status`) | 22 (9 multi-label) |
| `reschedule_delivery` | pedidos_logistica | confusable with `update_delivery_address` / `track_shipment` (delivery-time vocabulary) | 10 | 13 |
| `generate_return_label` | trocas_devolucoes | confusable with `create_return_request` (same return episode) | 7 | 13 |

Counts are by gold label only (`expected.acceptable_tools`). No alternative was needed: each skill
has a held-out tool with ≥7 dev and ≥13 test-v2 cases.

## Mechanism (nothing on the MCP server changes)

1. **Runtime catalog filter** — settings `catalog.exclude_tools: [...]`, applied in
   `routing_study/catalog.py` (`fetch_catalog` → `Catalog.without`) after the server fetch and
   after the SKILL.md `allowed-tools` consistency check. It removes the tools from `tools/list`,
   and the skill-frontmatter examples that are verbatim copies of an excluded tool's `_meta`
   examples. Everything derived from the catalog follows automatically: skill/tool
   `RouteOption`s, skill shots (round-robin over the remaining tools), DON'T USE FOR clauses
   that pointed to an excluded tool (dropped, since `avoid_clauses` keeps known tools only),
   the executor's tool schemas, and `catalog_hash`. The Redis cache key carries the exclusion,
   so a reduced catalog never overwrites the full one.
2. **Regex overlay** — `strategies.regex.overlay_paths: [...]` merges extra rule files over
   `rules_path` (overlay `defs` appended after the base defs; overlay rules appended per option
   id). `config_hash` covers the overlay bytes and the catalog exclusion.
   - `config/rq5/regex_rules_base.yaml`: the production rules **minus everything that exists
     because of the held-out tools**: their three tool-stage rule lists, the skill-stage rules
     whose vocabulary is specific to them (`{{RESCHEDULE}}` → pedidos_logistica, `{{LABEL}}`
     and `post(ar|agem)` → trocas_devolucoes) and the `RESCHEDULE` / `LABEL` defs.
     `get_refund_status` has no skill-stage rule of its own (its vocabulary, `{{REFUND}}`, is
     shared with `request_refund`).
   - `config/rq5/regex_overlay_original.yaml`: exactly the removed rules. A unit test asserts
     that base + this overlay equals production `config/regex_rules.yaml` (same expanded
     rules per option), so the split cannot drift silently.
   - `config/rq5/regex_overlay_engineered.yaml`: new rules for the three tools, written by the
     engineer under a timebox (see below).
3. **Manifest overrides** — a manifest entry may carry `overrides: {dotted.key: value}` patched
   over its experiment YAML (same mechanism as the `ROUTING__…` env patches), so one config
   file serves every condition and the version guard hashes the patched settings.

## Conditions (per strategy)

| Condition | Catalog | Regex rules | What it measures |
| --- | --- | --- | --- |
| **base** | 3 tools excluded | `regex_rules_base.yaml` | the "before" state; what happens to the held-out tools' cases when the tool does not exist |
| **zero** (zero-effort add) | full | `regex_rules_base.yaml` (regex gets **nothing** new) | adding the tool with only its catalog description + `_meta` examples/keywords; BM25 / embedding / classifier / LLM / Jev re-index or re-prompt from the catalog |
| **eng** (engineered add) | full | base + `regex_overlay_engineered.yaml` | adding the tool plus timeboxed regex rules; the other strategies need no extra work, so for them eng ≡ zero |
| **full** (reference, regex and hybrid only) | full | production rules | the current state: rules written over many iterations, with access to dev (and, for some suppressors, after test-v1 was read — B1) |

For BM25, embedding, classifier, LLM and Jev, eng and zero are the same run (no extra effort is
possible without changing the catalog, and the catalog text is the zero-effort input). Hybrid
(regex + classifier, convex fusion) is run in all four conditions because its regex member
changes.

### Engineer condition: honesty notes

- The engineer is an **AI agent** (Claude, the same session that implemented the harness), not
  a human. Rows and docs label it "agent-written rules, timeboxed".
- Inputs allowed: the three tools' catalog entries (description, WHEN TO USE, `_meta` examples
  and keywords), the SKILL.md playbooks and the existing base rules / defs. **Not allowed**:
  dev or test messages. The rules are therefore not tuned on dev, and the dev numbers of the
  eng condition are a held-out estimate for them.
- Contamination disclosure: the agent read the original production rules for these tools while
  building the base/original split, before writing the engineered ones. The engineered rules may
  be influenced by them; this biases eng towards full (optimistic for regex).
- Effort recorded in the overlay header: wall-clock minutes (start/end timestamps), timebox,
  non-comment lines, rules and defs.

## Metrics (per strategy × condition)

Case sets, from gold labels only (H = the 3 held-out tools):

- **affected**: `acceptable_tools ∩ H ≠ ∅` (dev 26, test-v2 48). Multi-label cases whose other
  acceptable tool remains (e.g. `get_payment_status`) can still be right in base.
- **other**: every remaining case.

Reported:

- joint / skill / tool accuracy on affected (base, zero, eng, full) — the main RQ5 number is
  joint on affected, zero vs eng vs base;
- `pred∈H`: share of affected cases whose predicted tool is a held-out tool (recall of the new
  tool, multi-label-agnostic);
- regressions on other cases, relative to base: `lost` = joint-correct in base and wrong after
  the add, `won` = the reverse, net Δ joint (pp); plus `stolen` = other cases routed to a
  held-out tool after the add (false positives of the new tool);
- effort: catalog authoring (lines of description + `_meta` examples + keywords of the 3 tools,
  common to every strategy), regex lines / rules / defs / minutes (eng), re-train seconds
  (BM25 index build, classifier fit, embedding of the new option texts with a cold vector
  cache; LLM/Jev: 0 s — the prompt is rebuilt from the catalog).

Error rows (infrastructure failures) count as wrong (ITT), as everywhere in the study.

## Runs

`study rq5` builds the table from the rescored manifest rows (`--manifest`, run names
`rq5-<split>-<strategy>-<condition>`) and, with `--retrain`, measures the re-train seconds.

- **dev, free** (`config/rq5_dev_manifest.yaml`): regex, bm25, embedding, classifier, hybrid ×
  base / zero / eng (+ full for regex/hybrid); all 151 dev cases. This is the end-to-end
  validation of the harness.
- **test-v2, free** (in `config/study_manifest.yaml`, section 10): the same matrix on all 349
  test-v2 cases.
- **test-v2, paid** (section 10): Jev, Haiku 4.5 and Sonnet (canonical prompt track: catalog
  text only, no tuned few-shots that could encode tool-specific effort), routing-only, 1 rep,
  base and zero, on the 48 affected test-v2 cases + a 60-case stratified regression sample of
  the other cases (`config/manifest/rq5_test_v2.ids`, 108 ids, built by
  `scripts/analysis/rq5_ids.py` from ids/categories/labels only). The zero entries reuse the
  rep-1 response cache of the main canonical runs (same case, rep and prompt) and cost ~0
  when those ran first.

## Limitations

- Skill descriptions and SKILL.md bodies still mention the held-out capability in base (only
  verbatim duplicated examples are removed). Base skill accuracy on affected cases is thus
  slightly optimistic; this understates the skill-level gain of the add.
- Regex calibration maps and hybrid fusion weights were fitted on dev with the full rules; they
  are not refitted per condition (accuracy in single mode does not depend on them).
- 3 tools, one engineer (an AI agent), one timebox: a case study of maintenance cost, not a
  population estimate.

## Dev validation (free strategies, 2026-09-30)

`uv run study run-manifest config/rq5_dev_manifest.yaml` then
`uv run study rq5 config/rq5_dev_manifest.yaml --retrain config/experiments/e10_classifier.yaml`
(Langfuse was unreachable, so the runs used `LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY=`;
tracing does not affect the rows). 151 dev cases per run, 0 errors. Dev is where the production
regex rules (`full`), the hybrid fusion and every free router's hyper-parameters were tuned, so
`full` and the absolute levels are optimistic here; the engineered overlay was NOT tuned on dev.

Held out: `get_refund_status`, `reschedule_delivery`, `generate_return_label`. affected = cases with a held-out tool among the acceptable tools; other = the rest. Δ other / lost / won are paired with `base` (joint, other cases); stolen = other cases routed to a held-out tool. Errors count as wrong (ITT).

| strategy | cond | n aff | joint aff | skill aff | pred∈H aff | n other | joint other | lost | won | Δ other (pp) | stolen | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | base | 26 | 3.8 | 80.8 | 0.0 | 125 | 56.0 | – | – | – | 0 | 0 |
| bm25 | zero | 26 | 61.5 | 88.5 | 61.5 | 125 | 54.4 | 4 | 2 | -1.6 | 6 | 0 |
| classifier | base | 26 | 15.4 | 80.8 | 0.0 | 125 | 77.6 | – | – | – | 0 | 0 |
| classifier | zero | 26 | 80.8 | 88.5 | 65.4 | 125 | 76.8 | 3 | 2 | -0.8 | 3 | 0 |
| embedding | base | 26 | 15.4 | 88.5 | 0.0 | 125 | 76.8 | – | – | – | 0 | 0 |
| embedding | zero | 26 | 88.5 | 96.2 | 76.9 | 125 | 76.8 | 2 | 2 | +0.0 | 2 | 0 |
| hybrid | base | 26 | 15.4 | 84.6 | 0.0 | 125 | 84.8 | – | – | – | 0 | 0 |
| hybrid | zero | 26 | 65.4 | 88.5 | 50.0 | 125 | 84.8 | 2 | 2 | +0.0 | 1 | 0 |
| hybrid | eng | 26 | 84.6 | 96.2 | 69.2 | 125 | 84.8 | 2 | 2 | +0.0 | 1 | 0 |
| hybrid | full | 26 | 88.5 | 96.2 | 73.1 | 125 | 84.8 | 2 | 2 | +0.0 | 1 | 0 |
| regex | base | 26 | 15.4 | 88.5 | 0.0 | 125 | 84.0 | – | – | – | 0 | 0 |
| regex | zero | 26 | 15.4 | 88.5 | 0.0 | 125 | 84.0 | 0 | 0 | +0.0 | 0 | 0 |
| regex | eng | 26 | 76.9 | 96.2 | 61.5 | 125 | 84.0 | 0 | 0 | +0.0 | 0 | 0 |
| regex | full | 26 | 88.5 | 96.2 | 73.1 | 125 | 84.0 | 0 | 0 | +0.0 | 0 | 0 |

### Effort of adding the 3 tools

- Catalog entry (input of every strategy, the zero-effort add): 18 description lines, 12 examples, 15 keywords.
- Regex, engineered (`eng`): 30 lines, 17 rules, 5 defs, 1.2 min wall clock (timebox 20 min; AI agent (Claude Opus): agent-written rules, timeboxed; not a human engineer).
- Regex, production (`full`, reference): 17 lines, 8 rules, 2 defs; minutes not recorded (iterated on dev).
- Regex, zero-effort: nothing new (the tool is unreachable by regex).
- Re-train after the add (s): BM25 index 0.009, classifier fit 0.087, embedding of 15 new option texts (cold) 4.29; hybrid = classifier fit + regex (0); LLM/Jev 0 (prompt rebuilt from the catalog).

Reading (dev, exploratory):

- Without the tool, every strategy gets the affected cases right only through a second
  acceptable label (4/26 multi-label refund/payment cases; BM25 1/26).
- Zero-effort add: the catalog-driven routers recover most of the affected cases (embedding
  88.5, classifier 80.8, BM25 61.5) with no measurable regression on the other 125 cases
  (Δ −1.6 to 0 pp; 2–6 cases stolen by the new tools). Regex stays at the base level: the new
  tools are unreachable.
- Engineered add: 17 agent-written rules (1.2 agent-minutes, catalog-only inputs) take regex
  from 15.4 to 76.9 joint on the affected cases, with zero regressions; the production rules
  (`full`, written on dev over many iterations) reach 88.5. Hybrid follows its regex member
  (65.4 zero → 84.6 eng → 88.5 full).
- Re-train cost is negligible for every catalog-driven router (BM25 9 ms, classifier fit
  87 ms, 4.3 s to embed the 15 new option texts cold on the local qwen3-embedding:8b).

## Paid estimate (test-v2, 108 cases × 1 rep per run)

| run | `study estimate` | dev-measured $/1k → this run |
| --- | --- | --- |
| rq5-test_v2-jev-base | $0.00 (no list price for `typesafe/jev-router`) | $0.93 → $0.10 |
| rq5-test_v2-haiku-base | $0.37 (measured) / $0.28 (a priori) | $5.32 → $0.57 |
| rq5-test_v2-sonnet-base | $0.56 (a priori) | $5.97 → $0.64 |
| three `*-zero` runs | cache hits of the main canonical runs' rep 1 | ~$0 (worst case, run first: same as base) |

Expected ≈ US$1.3; worst case (zero runs not cached) ≈ US$2.6, within the US$3 cap. The
a-priori bound assumes 900 prompt tokens per routing call; the measured prompts are ~1.1–2.2k
tokens, so the dev-measured column is the realistic one.
