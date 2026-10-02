# Tuning effort, phase 2 (dev / dev-L only)

Same protocol as phase 1 (`docs/tuning-effort.md`): 5-fold CV stratified by category, seed 0
(`scripts/analysis/tune_router.py`). "Nested" = per fold, the grid point that is best on the other
4 folds is scored on the held-out fold (an estimate of the tuning procedure). "Fixed" = the
committed config scored on all dev (chosen on the same data, optimistic). CIs are the paired
case bootstrap of prereg-v1 (10,000 resamples, seed 20260930) over the pooled held-out rows.
Calibration maps are fitted on train folds and scored on the held-out fold; with
`--calibrator both` the map (isotonic or Platt) is chosen per level by the pooled held-out Brier,
and it is **written into the config only if its cross-fitted ECE is lower than the raw ECE**
(`docs/decisions/2026-10-01-calibration-and-prompts.md`, prereg-v2 §5). The test splits were
never read.

## §A. Part A: cloud addendum on the 18-tool catalog (phase-1 dev, 151 cases)

Only the six new strategies are tuned; every phase-1 strategy is reused as frozen. Logs and
per-point JSON: `results/phase2a/` (gitignored); the summary JSONs are copied to
`docs/results/addendum-dev/`. Phase-2 constraint: no local model was run for any of this.

### Effort ledger

| strategy | configs evaluated | dev passes | wall-clock | paid calls | notes |
|---|---|---|---|---|---|
| E3c Cohere Embed v4 | 324 (phase-1 D1 grid, verbatim) + 3 (T by calibrated Brier) + 1 final `study run` = 328 | 328 (9 distinct query texts × 151 embedded once; vector cache) | ~3 min | ~US$ 0.004 | Grid script `results/phase2a/emb_grid.sh` = `results/phase2/emb_grid1.sh` with the config swapped. The Qwen-style instruction prefixes of the grid are kept as-is (same grid); Cohere also gets its own `input_type` (search_query / search_document). |
| E3t Titan v2 | 324 + 3 + 1 = 328 | 328 | ~1.5 min | ~US$ 0.001 | As E3c. |
| E10c probe on Cohere | 64 (phase-1 D4 probe grid) + 8 (C × history refinement around the 64-grid best: C ∈ {0.1, 0.3, 1, 3} × best C, other axes at the 64-grid best) + 1 final + 1 `study run` = 74 | 74 | ~30 s | < US$ 0.001 | Phase-1 refinement was {0.1, 0.3, 1, 3} around best C = 1; the same ratios are used around this model's best C (100 → {10, 30, 100, 300}). |
| E10t probe on Titan | 64 + 8 (best C = 1 → {0.1, 0.3, 1, 3}) + 1 + 1 = 74 | 74 | ~30 s | < US$ 0.001 | As E10c. |
| E6m Ministral 3 8B | 1 (P0 only; no prompt search) + calibration | 1 (the coordinator's dev run, response cache) | – | ~US$ 0.07 (dev run) | Isotonic maps (the phase-1 LLM procedure, `select_prompts.py`). |
| E6n Nemotron Nano 9B v2 | 1 (P0, `/no_think`) + calibration | 1 | – | ~US$ 0.03 (dev run) | As E6m. |

Human/agent time: about 1 h of agent time for all six, mostly waiting on the two grids. No rule
writing, no reading of dev errors to edit anything: every choice is a grid argmax or the
pre-declared calibration rule.

### Before → after (dev, 5-fold CV)

skill/tool are the fixed config on all dev. ECE and Brier read raw → calibrated (cross-fitted).
p50/p95 are ms per case (skill + tool stage) as recorded on dev, where Bedrock calls ran at
concurrency 2 from the Mac in São Paulo to `sa-east-1`: **not** the benchmark latency (that
comes only from the `lat-a-*` blocks of `config/addendum_manifest.yaml`).

| router | config | skill | tool | joint fixed [95% CI] | joint nested [95% CI] | skill ECE / Brier | tool ECE / Brier | map written | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| E3c Cohere v4 | before (first grid point: max_example, T 0.02, no history, no shots, no instruction) | 62.3 | 47.7 | 47.7 | – | 0.219 (raw) | 0.353 (raw) | – | 570 / 1424 |
| E3c Cohere v4 | **after**: topk_vote k 5, T 0.1, history 2, shots, no instruction | 73.5 | 62.9 | 62.9 [55.0, 70.9] | **59.6 [51.7, 67.5]** | 0.069→0.047 / 0.167→0.169 (Platt) | 0.120→0.050 / 0.224→0.207 (isotonic) | skill + tool | 562 / 1382 |
| E3t Titan v2 | before (same baseline point) | 58.9 | 45.0 | 44.4 | – | 0.215 (raw) | 0.367 (raw) | – | 138 / 358 |
| E3t Titan v2 | **after**: centroid, T 0.02, history 1, shots, no instruction | 73.5 | 61.6 | 60.3 [52.3, 68.2] | **60.3 [52.3, 68.2]** | 0.094→0.070 / 0.172→0.172 (isotonic) | 0.225→0.061 / 0.233→0.183 (Platt) | skill + tool | 136 / 226 |
| E10c probe (Cohere) | **after**: C 10, shots, description, no instruction, history 0 | 68.9 | 60.9 | 57.0 [49.0, 64.9] | **53.6 [45.7, 61.6]** (64-pt) / 56.3 [48.3, 64.2] (refinement) | 0.103→0.103 / 0.200→0.192 (isotonic) | 0.230→0.121 / 0.256→0.198 (isotonic) | tool only (skill ECE 0.1027→0.1028: not lower) | 568 / 1359 |
| E10t probe (Titan) | **after**: C 0.1, shots, description, no instruction, history 0 | 70.9 | 62.3 | 60.9 [53.0, 68.2] | **60.9 [53.0, 68.9]** (64-pt) / 59.0 [51.0, 66.9] (refinement) | 0.441→0.070 / 0.397→0.179 (isotonic) | 0.440→0.219 / 0.454→0.234 (isotonic) | skill + tool | 135 / 215 |
| E6m Ministral 3 8B | P0, T 0 | 88.7 | 80.8 | 79.5 [72.8, 86.1] (CV); 78.8 [72.2, 85.4] in the `study run` ITT (1 error row, recovered on a later retry) | = fixed (one point) | 0.093→0.041 / 0.104→0.089 (isotonic) | 0.142→0.029 / 0.170→0.144 (isotonic) | skill + tool | 1008 / 1174 |
| E6n Nemotron Nano 9B v2 | P0, T 0, `/no_think` | 86.8 | 78.8 | 78.1 [71.5, 84.8] | = fixed (one point) | 0.061→0.012 / 0.106→0.103 (isotonic) | 0.146→0.092 / 0.177→0.162 (isotonic) | skill + tool | 1553 / 2310 |

Phase-1 local peers on the same dev (from `docs/tuning-effort.md` and `config/prompt_selection.yaml`):
qwen3-embedding 8B E3 nested 77.5, local probe E10 76.2–76.8, Qwen3-8B E6b 82.2 (CV).

### 8B routers: full-P0 cost and parse-failure check (T0.3 / T2.3)

| model | prompt tokens per call (mean) | output tokens per call | US$ per 1k cases (skill + tool) | parse failures (calls) | error rows (ITT, wrong) |
|---|---|---|---|---|---|
| Ministral 3 8B | 1,167 | 79 | 0.449 | 1 / 302 (0.3%) on the first pass; 0 after the retry | 1 / 151 (0.7%) → 0 |
| Nemotron Nano 9B v2 | 1,340 | 69 | 0.226 | 2 / 302 (0.7%) | 2 / 151 (1.3%) |

Both are under the 2% threshold, so **no format-only fix** was applied. The real P0 prompt is
about 1.2–1.3k tokens per call, not the 2.3k assumed in plan §5: the plan's per-case estimate
(Ministral 0.00085, Nemotron 0.00035) is about 2× / 1.5× too high, so A3 (test-v2 8B ×2, 399
cases) is about US$ 0.27 instead of 0.50.

### What moved the numbers

- **Managed embedders are far below the local qwen3-embedding 8B on this task** (nested 59.6 /
  60.3 vs 77.5). The gap is in both stages and largest in `fora_escopo` for Cohere (13% joint).
- Shots are selected for both embedders (as for qwen3); history helps (Cohere 2 turns, Titan 1).
- No instruction prefix wins for either: the Qwen-style `Instruct: …\nQuery:` prefix costs both
  models 5–15 points. That is expected (they are not instruction-tuned that way); the grid was
  kept identical to phase 1 on purpose.
- Cohere prefers kNN voting (`topk_vote`, k 5) over centroid, unlike qwen3 and Titan.
- The probes do not beat their own embedding router (E10c 53.6–56.3 vs E3c 59.6; E10t 59.0–60.9
  vs E3t 60.3), unlike the local probe, which matched the local router.
- The managed 8B LLMs land within 3–4 points of the local Qwen3-8B on dev (79.5 / 78.1 vs 82.2);
  family A tests that gap on test-v2 with a 3 pp NI margin.

## §B. Large catalog (62 tools, 10 skills; dev-L)

### regex (E1-L): catalog-only rules, before any dev-L read (T5.1, part 1)

`config/regex_rules_l.yaml` was written from the catalog only: tool descriptions, WHEN TO USE
quotes, `_meta` examples and keywords (`mcp_server/tools_list_large.json`), the SKILL.md
disambiguation rules and the G1–G12 table of `docs/catalog-large.md`. **No dataset file was
read** (dev-L did not exist yet; no phase-1 split was opened either). The dev-L error round comes
later and is logged as a separate row.

| step | what | agent wall-clock | human | dev passes | paid calls |
|---|---|---|---|---|---|
| catalog rules | base = phase-1 rules copied unchanged; suppressors on the originals; rules for 7 new skills, 42 new tools, 2 new globals; 2 fix rounds on the in-sample checks below | ~0.4 h (2026-10-02 00:13–00:35) | 0 | 0 | 0 (US$ 0) |
| dev-L round | read the 68 joint errors of the catalog-only rules on dev-L (`tune_router.py --split dev_l --errors`), then 2 edit batches + 2 CV re-runs; additive only (rules tagged `dev-L round`) | 2026-10-02 00:39:56–00:43:46 by `date` stamps (agent time) | 0 | 4 (2 points each, history 0/2) | 0 (US$ 0) |

Timebox (plan §3, risk R1): 4 h for the whole regex effort. Used so far: ~0.4 h, so ~3.6 h
remain for the dev-L error round; R1 allows one more logged 2 h round after the dev-L CV and
nothing beyond it.

**Rule counts** (patterns; a pattern may be an alternation):

| | option ids | rules | of which suppressors (< 0) | defs |
|---|---|---|---|---|
| phase 1 (`regex_rules.yaml`, 18 tools) | 22 | 79 | 7 | 30 |
| large (`regex_rules_l.yaml`, 62 tools) | 73 (10 skills + `__global__` + 62 tools) | 235 (91 skill stage, 144 tool stage) | 64 | 46 |
| – inherited from phase 1, unchanged | 22 | 79 | 7 | 30 (OFF_SCOPE edited, see below) |
| – added to the 22 original ids | | 43 | 39 | |
| – new ids (7 skills, 42 tools, 2 globals) | 51 | 113 | 18 | 16 new |

File: 478 lines (phase 1: 181).

**Decisions.**

- *The original positive rules are untouched.* All 79 phase-1 rules are byte-identical. On the
  original ids I added only suppressors (G1–G12), the two new-global rules on `__global__`
  (contact change, protocol) and one escalate_to_human rule ("esqueci a senha / não consigo
  entrar", the example the large overlay adds). On the 71 catalog examples shared with phase 1,
  the large rules route exactly the same set as the phase-1 rules do on the small catalog
  (54/71 vs 55/72; **0 regressions, 0 gains**). This keeps the original tools comparable
  across catalogs. The remaining misses on original tools are phase-1 misses, left for the
  dev-L round.
- *OFF_SCOPE edited.* "nota fiscal" and "preços" are in scope in the large catalog
  (`docs/catalog-large.md` §3), so they were dropped, and "senha|login|atacado|estoque" were
  added (escalate_to_human's large description).
- *Suppressors carry the G1–G12 rules at the skill stage.* The tool stage only offers one
  skill's tools + the 5 globals, so a cross-skill group is decided at the skill stage. Each
  group's "domain marker" is a def (CARD, SUB, TECH, SELLER, INVOICE, RECEIPT, PROMO,
  PRICE_DROP, LOYALTY, DEBT, CONTACT, PROTOCOL). The original skill that shares the trigger
  gets a suppressor (-0.6 or -1.0) on that marker: e.g. pedidos_logistica −1.0 on SUB/TECH
  (G4, G5), pagamentos_reembolsos −1.0 on CARD/SELLER (G1, G2) and on cashback/points (G3),
  trocas_devolucoes −1.0 on TECH (G7) and on CNPJ/"nota de devolução"/seller refusal (G10). The
  original tools get the same suppressors at the tool stage (e.g. cancel_order, dispute_charge,
  track_shipment), in case a misrouted skill offers them.
- *Following the SKILL.md rules literally where they are asymmetric.* G10: a plain return of a
  partner-seller product stays create_return_request (marketplace −0.6 on "devolver" unless
  "recusou"); only a refusal goes to open_seller_mediation. G7: "ainda está na garantia?"
  stays check_return_eligibility; "até quando vai a garantia" / "garantia estendida" goes to
  check_extended_warranty.
- *Catalog-shaped tokens.* Coupon codes (`[a-z]{3,}\d{2,3}`, e.g. CASA50) and gift-card codes
  (`presente-…`) are PROMO markers; "nota 5" is excluded from the INVOICE marker (rate_seller).
  Subscription goods named in the catalog (ração, fraldas, cápsulas, refil) are a 0.6 hint.

**In-sample checks (catalog phrases; the rules were written against them, so these are a
coverage floor, not an accuracy estimate).** End-to-end = skill stage over 11 options, then tool
stage over the skill's tools + 5 globals; a tie or no match is a miss.

| check | hits |
|---|---|
| `_meta` examples, all 62 tools (248) | 231 (93.1%); every tool ≥ 2/4 |
| – the 44 new tools (176) | 176 (100%) |
| – the 18 original tools (72) | 55 (76.4%) = phase-1 rules on the small catalog |
| WHEN TO USE quotes (121) | 118 (97.5%); the 3 misses are original tools |
| SKILL.md frontmatter examples, skill stage (50) | 50 (100%) |
| G1–G12 probes written from the SKILL.md rules (34) | 34 (100%) |

Per skill (`_meta` examples): assinaturas, assistencia_tecnica, cartao_loja_crediario,
fidelidade_cashback, marketplace_vendedores, notas_fiscais_cadastro and promocoes_precos 24/24
each; `__global__` 19/20; trocas_devolucoes 16/20; pagamentos_reembolsos 15/20;
pedidos_logistica 13/20.

Expect a large drop on dev-L: the phase-1 regex lost 32 pp from dev to test, and these rules saw
no user phrasing at all. Tests: `tests/routers/test_regex_rules_l.py` (≥ 2 examples per tool,
the phase-1 phrase tests on the large option sets, one probe per G1–G12 tool).

#### dev-L round (T5.1 part 2): what changed and what it bought

The round read the dev-L errors once, so its CV number is optimistic, like the phase-1 regex
row: the CV only re-selects `history_turns`, and the rules were written on the same cases.

- Rules 235 → 298 (suppressors 64 → 93), defs 46 → 48 (`INJECT`: prompt injection / mass
  action → `__global__` + escalate_to_human; `NO_REPLY`: "aguardo retorno" is not a return).
  File 478 → 554 lines. The 79 phase-1 positive rules are still byte-identical.
- Widened catalog markers: entity-id prefixes from the large mock DB contract (ASS-, OS-,
  VALE-, protocol prefixes ATD/NFC/MED/AJC/CCL; promotion codes), "cartão de vocês / fatura do
  cartão / TX-…" → store card, "comprova…/comprobatório" → receipt, "documento fiscal",
  "pontinhos/patente/bonificação" → loyalty, "terceiro/de quem estou comprando/lojão" → seller,
  off-scope "parceria/seguidores/representação comercial/revenda/emprego".
- Tool-stage fixes on new tools (block vs contest, gift-card balance vs redeem, reschedule
  technical visit, return label "adesivo", resend invoice "retransmissão", seller report vs
  contact, pause "congelar").

| | skill | tool | joint (fixed = nested here) [95% CI] | skill ECE raw→cal | tool ECE raw→cal |
|---|---|---|---|---|---|
| catalog-only rules | 69.3 | 58.0 | 54.7 [46.7, 62.7] | 0.115 | 0.229 |
| after the dev-L round | 89.3 | 83.3 | **82.7 [76.7, 88.7]** (optimistic) | 0.110→0.058 (Platt) | 0.214→0.082 (Platt) |

Remaining errors are mostly multiturno ("e o outro?") and ambiguo; per category after the
round: direto 86.7, parafrase 81.1, ambiguo 66.7, multiturno 53.3, fora_escopo 86.7,
adversarial 75.0 (joint, first edit batch). Timebox used: ~0.5 h of the 4 h (+2 h) budget.

### Other strategies on dev-L (T5.1–T5.3)

Embedder: **Titan v2** for E3-L/E10-L/E11-L, per the Part A recommendation (dev CV ties Cohere
within noise, ~4× faster, ~6× cheaper); no local model. Logs and per-point JSON:
`results/phase2l/` (gitignored); grid scripts there (`bm25_grid.sh`, `emb_grid.sh`,
`emb_T.sh`, `probe.sh`, `llm_p0.sh`). Tuned blocks: `docs/results/phase2-dev-l/tuned_blocks.yaml`,
applied with `scripts/analysis/apply_tuned_l.py`. Maps written only when the cross-fitted ECE
is lower than raw.

| strategy | configs evaluated (dev-L passes) | wall-clock | paid | joint nested [95% CI] | fixed joint | skill ECE raw→cal | tool ECE raw→cal | map | p50 / p95 ms | US$/1k cases |
|---|---|---|---|---|---|---|---|---|---|---|
| E2 BM25 grid 1 | 512 | 4.5 min | 0 | 50.0 [42.0, 58.0] | 54.7 | – | – | – | 8 / 17 | 0 |
| E2 BM25 grid 2 (around grid-1 best: char, shots, no quotes, okapi) | 432 | ~1.5 h (host slept) | 0 | **52.7 [44.7, 60.7]** | 56.0 | 0.511→0.065 (Platt) | 0.346→0.106 (Platt) | skill + tool | 19 / 37 | 0 |
| E11 hybrid, convex (7 member sets × 11 alphas) | 77 | ~40 min | cached embeddings | **81.3 [75.3, 87.3]**: regex + classifier, alpha 0.5 (same as phase 1) | 82.7 | 0.112→0.040 (Platt) | 0.116→0.042 (isotonic) | skill + tool | – | ≈0.003 |
| E11 logistic stacker (regex, bm25, embedding; `fit_hybrid.py`) | 3 L2 values, inner CV | ~2 min | cached | 80.0 ± 8.7 (below convex: not used) | – | – | – | – | – | – |
| E3 Titan embedding | 324 (D1 grid verbatim) + 3 (T by calibrated Brier: T 0.02) | ~2 min + 1 min | ~US$ 0.002 | 61.3 [53.3, 69.3] | 64.7 | 0.083→0.118 | 0.186→0.133 (isotonic) | tool only | 161 / 250 | ≈0.003 |
| E10 probe on Titan | 64 (D4 grid) + 8 (C {100,300,1000,3000} × history) | ~1 min | < US$ 0.001 | 66.0 [58.0, 73.3] (both) | 66.7 | 0.060→0.090 | 0.115→0.085 (isotonic) | tool only | 176 / 395 | ≈0.003 |
| E6 Haiku 4.5, P0 | 1 | ~4 min | US$ 1.08 | 84.0 [78.0, 89.3] | 84.0 | 0.065→0.038 | 0.070→0.106 | skill only | 3651 / 4870 | 7.18 |
| E6m Ministral 3 8B, P0 | 1 | ~3 min | US$ 0.10 | 78.7 [72.0, 84.7] | 78.7 | 0.145→0.076 | 0.148→0.059 | skill + tool | 841 / 1341 | 0.70 |
| E6n Nemotron Nano 9B v2, P0 | 1 | ~3 min | US$ 0.05 | 73.3 [66.0, 80.0] | 73.3 | 0.156→0.101 | 0.199→0.022 | skill + tool | 1397 / 1936 | 0.33 |
| E4 Jev, P0 | 1 | ~4 min | US$ 0.19 (OR) | 86.7 [80.7, 92.0] | 86.7 | 0.057→0.029 | 0.023→0.047 | skill only | 3620 / 7629 | 1.28 |
| Sonnet 5 P0 (shadow only, OQ-1) | 1 | ~4 min | US$ 1.13 | 84.0 [78.0, 89.3] | 84.0 | 0.123→0.022 | 0.047→0.037 | skill + tool | 5840 / 10058 | 7.52 |

- **Parse failures:** Ministral 2/300 calls (2 rows, 1.3% ITT), Jev 1, Sonnet 1, Haiku and
  Nemotron 0: every model under 2%, so **no format-only fix**.
- **Haiku cache (X3):** 0 cache reads: the large P0 prompt is ~2.7k tokens per call, under the
  4,096-token Haiku cache minimum. Sonnet (1,024 minimum) reads ~2.6k cached tokens per call.
- p50/p95 are dev-L tuning latencies at concurrency 2–4, **not** the benchmark.

- **Learned deferral** (`fit_hybrid.py`, skill stage, P(regex correct)): CV AUROC 0.654 learned
  vs 0.732 for regex's own calibrated confidence; as in phase 1, the single-confidence gate stays.

### Cascade thresholds (T5.4)

Dev-L shadow `freeze-dev-l-shadow-r1` (`config/freeze_dev_l_manifest.yaml`, E9-L deciding, shadow
set regex/bm25/embedding/llm(Sonnet)/jev/hybrid/classifier, Sonnet 1 rep on dev-L only per OQ-1):
150/150, 0 errors; its Sonnet and Jev calls were response-cache hits of the T5.3 passes and of a
warm-up shadow with the same E9-L routing blocks. Rule (a) of prereg-v1 §4: max joint s.t. routing
cost ≤ 0.5 × Sonnet P0 dev-L cost per case (7.522/1k → **US$ 0.003761/case**), grid 0.50..0.99,
5-fold cross-fitted. Reports: `docs/results/phase2-dev-l/cascade-thresholds-dev-l.md`.

| cascade | thresholds (rule (a)) | dev joint | CV held-out joint [95% CI] | CV US$/1k routing | skill-stage coverage per step (dev) |
|---|---|---|---|---|---|
| E7-L regex → Jev | regex 0.88 | 86.7 | 86.0 [80.0, 91.3] | 1.04 | regex 105/150 (70%), Jev 45 |
| E8-L regex → Sonnet | budget infeasible → phase-1 fallback, unconstrained (a): regex 0.88 | 83.3 | 83.3 [77.3, 88.7] | 6.40 | – |
| E9-L regex → Jev → Sonnet | regex 0.88, Jev 0.76 / tool Jev 0.50 | 86.7 | **86.0 [80.0, 91.3]** | 1.06 | regex 105 (70%), Jev 45, Sonnet 0 |
| E12-L hybrid → Jev → Sonnet | hybrid 0.78, Jev 0.76 / tool Jev 0.50 | 84.0 | 82.7 [76.0, 88.7] | 1.07 | hybrid 118 (79%), Jev 32 |

References (E9-L, dev): always-Sonnet 80.0 at US$ 8.82/1k; always-first 80.0; oracle 88.7;
random deferral at the same rates 80.3. E9-L thresholds equal the phase-1 values.

### e2e validation (T5.5)

`config/dev_l_e2e_manifest.yaml`: E0-L and E9-L on the same 40 stratified dev-L cases
(`config/manifest/dev_l_e2e_validation_40.ids`), Sonnet 5 executor, 1 rep. Both runs COMPLETE,
0 error rows; every row has a symmetric score (no `None`), 0 unknown tool calls.

| arm | e2e legacy [95% CI] | e2e sym [95% CI] | skill (legacy / sym) | billed US$/turn | study US$/turn | resolved_by |
|---|---|---|---|---|---|---|
| E0-L native | 60.0 [45.0, 75.0] | 65.0 [50.0, 80.0] | 87.5 / 80.0 | 0.0139 | 0.0139 | native 40 |
| E9-L | 57.5 [42.5, 72.5] | 60.0 [45.0, 75.0] | 92.5 / 77.5 | 0.0165 | 0.0178 | regex 28, Jev 12 |

- **Scorer fix found here** (09c1d12): `rescore_file` scored large-split rows against the 18-tool
  `tools_list.json`, so every new tool's call was an unknown tool; E0-L read 22.5% legacy. The
  default snapshot is now per split (`dev_l`/`test_l` → `tools_list_large.json`).
- **Cost per turn, measured** (replaces the plan §5 ×1.25 multiplier): E0-L 0.0139 (plan 0.0113;
  smoke 0.029 was cache writes on 5 turns), E9-L 0.0165 billed (plan 0.0090). For test-L (300):
  B13 E0-L ≈ US$ 4.2 (plan 3.39), B14 E9-L ≈ US$ 5.0 (plan 2.69), B15 ≈ 5.0, B16 (60+60) ≈ 1.8.
- The budget guard of `study run` refused E9-L on its a-priori bound (US$ 3.11 > 2.95 left); the
  manifest ran a 10-case batch first, then the rest on the measured cost (US$ 0.67 projected).
- The 10th case of the first batch hung across a host sleep; the run was killed and resumed by
  (case, rep) through the 40-id manifest: no infra-error rows were left.
