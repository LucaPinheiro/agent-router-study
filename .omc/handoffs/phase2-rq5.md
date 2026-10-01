# Phase 2 D7 — RQ5 leave-tools-out harness (handoff)

Design + dev results: `docs/rq5-design.md`. Status: exploratory (not pre-registered unless
promoted at prereg-v1).

## What exists
- Held out: get_refund_status (pagamentos), reschedule_delivery (pedidos), generate_return_label
  (trocas). Record: `config/rq5/effort.yaml`.
- `catalog.exclude_tools` (settings `CatalogConfig`) → `Catalog.without()` applied in
  `fetch_catalog` after the allowed-tools check; drops tools + verbatim-duplicated skill
  examples; Redis key gets `:exclude=...` suffix. MCP server untouched.
- `strategies.regex.overlay_paths` (dumped only when non-empty → existing config hashes
  unchanged; verified e1 hash 8bd27de54306 before/after). `RegexRules.load(path, overlays)`.
- `config/rq5/regex_rules_base.yaml` (production minus held-out rules/defs),
  `regex_overlay_original.yaml` (the removed lines; test asserts base+original == production),
  `regex_overlay_engineered.yaml` (agent-written, timeboxed: 17 rules, 5 defs, 30 lines,
  1.2 wall-clock min, catalog-only inputs; disclosure: the agent had read the original rules).
- Manifest entries accept `overrides: {dotted.key: value}` (→ `load_settings(patches=...)`,
  unknown top-level key = error); config_hash covers overlays' bytes and the exclusion.
- `study rq5 <manifest> [--split] [--retrain <config>] [--out]`: table from rescored
  `rq5-<split>-<strategy>-<base|zero|eng|full>` runs + effort + re-train seconds.
- `scripts/analysis/rq5_ids.py` → `config/manifest/rq5_test_v2.ids` (48 affected + 60
  stratified regression sample = 108; reads only id/category/labels).
- `config/rq5_dev_manifest.yaml` (dev, free) and section 10 of `config/study_manifest.yaml`
  (test-v2: 14 free runs on all 349 cases, priority 90; Jev/Haiku/Sonnet canonical base+zero on
  the 108 ids, priority 95).
- Tests: `tests/routers/test_rq5.py` (17).

## Dev table (151 cases, 0 errors)
| strategy | cond | joint aff (26) | joint other (125) | Δ other pp | stolen |
| --- | --- | --- | --- | --- | --- |
| regex | base / zero / eng / full | 15.4 / 15.4 / 76.9 / 88.5 | 84.0 all | 0 | 0 |
| bm25 | base / zero | 3.8 / 61.5 | 56.0 / 54.4 | -1.6 | 6 |
| embedding | base / zero | 15.4 / 88.5 | 76.8 / 76.8 | 0.0 | 2 |
| classifier | base / zero | 15.4 / 80.8 | 77.6 / 76.8 | -0.8 | 3 |
| hybrid | base / zero / eng / full | 15.4 / 65.4 / 84.6 / 88.5 | 84.8 all | 0.0 | 1 |
Re-train: BM25 0.009 s, classifier fit 0.087 s, embed 15 new texts cold 4.29 s; LLM/Jev 0.

## Paid (not run)
Base: Jev ~$0.10 (estimate $0.00, no list price), Haiku $0.37 measured (~$0.57 by dev $/1k),
Sonnet $0.56 a priori (~$0.64 by dev $/1k) → ≈ $1.3. Zero runs are cache hits of the main
canonical runs' rep 1 if those run first (priority 20–50 < 95); worst case ≈ $2.6 (< $3).

## Notes / caveats for the lead
- Langfuse (localhost:3300) timed out and docker CLI hung during the dev run: the first
  manifest pass crashed in `Runner._upload`; resumed with `LANGFUSE_PUBLIC_KEY=
  LANGFUSE_SECRET_KEY=`. Multi-run manifests also log "Event loop is closed" Langfuse warnings
  (pre-existing: one Langfuse client across several `asyncio.run`).
- Shared Redis catalog key held a catalog negotiated at protocol 2025-11-25 by another process
  (same content, different `catalog_hash` 823546e24af8 vs 33f89f3db4f5). rq5-dev-regex-zero
  carries 33f89…, the other full-catalog runs 823546…; routing content identical.
- `full` regex/hybrid are optimistic on dev (rules written on dev); the paid canonical zero ≡
  main canonical runs.
