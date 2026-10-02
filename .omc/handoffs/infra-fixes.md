# Infra fixes before the paid study (Langfuse multi-run loss, protocol-dependent catalog_hash)

Branch `fix/review-findings-and-rescore`. Free repro only: `e1_regex` / `e2_bm25`, routing-only,
dev, 5 cases per entry. Manifests used: `/tmp/infra/manifest_{before,after,final,down}.yaml`
(2 entries each). Counter: `/tmp/infra/lfcount.py` (reads `/api/public/v2/observations`,
`/api/public/v3/scores`, `/api/public/experiments` and `/api/public/experiment-items`, the last
two need `fromStartTime`).

## BUG 1 — Langfuse data lost in multi-run manifests

**Root cause.** `run_case` linked every turn to the experiment with
`tracing.client().async_api.dataset_run_items.create(...)`. `async_api` wraps ONE
process-wide `httpx.AsyncClient`, and its pool keeps keep-alive connections bound to the event
loop that opened them. `study run-manifest` runs each entry in its own `asyncio.run`. In entry
2 and later, the pool reuses a connection from the closed loop, so closing it calls
`loop.call_soon` on a closed loop and raises `RuntimeError: Event loop is closed`. The
`except Exception` around the link swallowed the error and logged it as a warning. The turn
then got no `langfuse.experiment.*` attributes and no dataset-run-item row. If every link of a
run fails, `dataset_run_id` stays None and the run-level scores are lost too. Spans and trace
scores are not affected: they use the SDK's thread-based OTel exporter and score queue, which
do not depend on the event loop.

**Evidence. Before the fix** (`infra-before-*`, 4 "Event loop is closed" tracebacks in the log):

| run | traces with obs | trace scores | experiment items | run scores |
|---|---|---|---|---|
| infra-before-regex (entry 1) | 5/5 | 35/35 | **5/5** | 6 |
| infra-before-bm25 (entry 2) | 5/5 | 35/35 | **1/5** | 6 (on an experiment of 1 item) |

**Fix** (`tracing/langfuse.py`, `eval/runner.py`):
- The link now goes through the SYNC API (`client().api.dataset_run_items.create`) inside
  `asyncio.to_thread`, so it does not depend on any event loop. It uses `awith_retry`: backoff
  of 0.5/1/2/4 s on transport errors, timeouts, 429 and 5xx. 4xx errors are not retried. After
  the last retry the run still does not crash: it counts `link_failures` and logs a summary at
  the end of the run. The SDK's `async_api` is no longer used anywhere.
- `tracing.preflight()` is the first step of `Runner.run`, before model validation, the budget
  check, Ollama preload and any case. It calls `api.projects.get` with the same retries. If
  that fails, it raises `LangfuseUnavailableError`.
- `_upload` (create_dataset and each create_dataset_item, which are upserts keyed by case id)
  and `register_prompts` are retried with `with_retry`. If they still fail, they raise
  `LangfuseUnavailableError`. This also happens before any case runs.
- The manifest catches `LangfuseUnavailableError` and logs
  `LANGFUSE <run>: …; stopping the manifest (nothing spent)`. The entry gets state
  `langfuse` (exit 1) and the manifest stops. `study run` exits with code 2.

**Evidence. After the fix** (`infra-after-*`, 0 warnings, then `infra-final-*` with both fixes):

| run | traces with obs | trace scores | experiment items | run scores |
|---|---|---|---|---|
| infra-after-regex / -bm25 | 5/5, 5/5 | 35/35, 35/35 | **5/5, 5/5** | 6, 6 |
| infra-final-regex / -bm25 | 5/5, 5/5 | 35/35, 35/35 | **5/5, 5/5** | 6, 6 |

Langfuse down (`LANGFUSE_HOST=http://localhost:3999`, `infra-down-*`): 4 retries, then
`LANGFUSE infra-down-regex: … Connection refused; stopping the manifest (nothing spent)` after
about 8 s. No results file was created and the second entry never started.

## BUG 2 — catalog_hash depended on the negotiated MCP protocol

**Root cause.** `mcp_client` built `fastmcp.Client(transport)` with the default
`mode="auto"`. In that mode, `negotiate_auto` (mcp `client/_probe.py`) probes
`server/discover` at 2026-07-28. On ANY rpc error from the probe, it silently falls back to the
`initialize` handshake, which negotiates `LATEST_HANDSHAKE_VERSION` = **2025-11-25**. Such errors
include a client-side `REQUEST_TIMEOUT` (-32001) under load, a 5xx, or a discover result that is
not conformant. The legacy session also returns the tools with another JSON key order inside
`inputSchema` (`properties, type, …` instead of `type, additionalProperties, properties, …`).
`Catalog.hash` hashed `to_json()`, which includes `protocol_version`, `url` and `ttl_s` and
keeps key order. So the same content got a different hash. The Redis key used the CONSTANT
`mt.LATEST_PROTOCOL_VERSION`, not the version actually negotiated. A fallback catalog was
therefore stored under the 2026-07-28 key and served to every other process.

**Repro.** On a healthy server, 40 concurrent `auto` clients all negotiate 2026-07-28. Two
things reproduce the bug: a forced `mode="legacy"`, or `auto` with the discover probe failing
with `REQUEST_TIMEOUT`. Both return `2025-11-25` with hash **823546e24af8**, exactly the
foreign hash from phase2-rq5. A clean fetch returns `2026-07-28` with **33f89f3db4f5**. Field
by field, the two catalogs differ only in `protocol_version` and in the key order of the 18
`inputSchema` objects.

**Fix** (`catalog.py`):
- `PROTOCOL_VERSION = "2026-07-28"` is pinned explicitly. Import fails if the SDK drops it.
  `mcp_client` uses `Client(..., mode=PROTOCOL_VERSION)`, so there is no probe and no fallback.
  The in-process `Client(mcp)` calls in `eval/rq5.py`, `scripts/analysis/{tune_router,bench_local}.py`
  and the tests are pinned too.
- `fetch_catalog` refuses a session at any other version (`RuntimeError`). It reads the
  instructions with an explicit `server/discover` (`send_discover`), because a pinned client
  adopts a synthesized result that has no instructions. This call fails loudly and never falls
  back.
- `Catalog.hash` is now computed over `content()`: instructions, tools and skills. JSON-object
  keys are sorted, except the members of a schema's `properties`, which keep server order.
  Tools and skills stay lists in server order, because order shapes the prompt bytes. It
  excludes protocol_version, url and ttl_s. `to_json` (the Redis payload) is unchanged.
- The Redis key keeps `mcp:catalog:<url>:<PROTOCOL_VERSION>` (the pinned version). An entry
  whose `protocol_version` differs is ignored with a warning and refetched, which protects
  against older unpinned writers.
- Provenance: `Runner.meta["catalog_hash"]` (rows, Langfuse metadata, the `ingest` span) and
  `assert_same_version`, the resume guard the manifest runs through, now use the content hash.
  The live catalog hashes to **128584617807** whatever the era: a legacy-era catalog rebuilt
  from a 2025-11-25 session gives the same 128584617807.

**Hash migration.** The new hash replaces the old one, with no alias. Rows written before this
commit carry the old, protocol-dependent value. 33f89f3db4f5 and 823546e24af8 are both the
same content as 128584617807 (checked live). The study manifest has no `.partial` and no
partially written run, so nothing needs resuming across the change. Rows written before the
change and resumed after it would be refused by `assert_same_version`. That is intended: a
resume must not mix hash definitions silently.

**Side effect (expected).** Each turn's trace has one fewer observation (13 → 12 in the
repro): the pinned `McpTools` client no longer sends `MCP send server/discover` before
`tools/call`. That is one less round trip per turn. `tests/integration/test_trace_tree.py` waits
for `min_obs=20` on paid e2e traces, and I did NOT run it (paid). Check it in the first paid
smoke.

## Tests (new)
- `tests/test_catalog.py`: content hash ignores protocol/url/ttl/schema key order; changes with
  instructions, description, tool order, properties order and skill markdown; clients and the
  Redis key are pinned to 2026-07-28; a Redis entry from another era is never served; a legacy
  session is refused; a pinned in-process fetch has the server instructions.
- `tests/test_tracing_retry.py`: retry on timeout/5xx, give up after the last attempt, no retry
  on 4xx, `awith_retry` works across 3 successive `asyncio.run`, preflight fails fast / no-op
  without tracing.
- `tests/eval/test_manifest.py`: a `LangfuseUnavailableError` stops the manifest at the first
  entry with no results; resume accepts rows whose catalog came from another era with the same
  content, and refuses the old protocol-dependent hash.

## Verify
- `uv run ruff check .` / `uv run ruff format --check .`: clean.
- `uv run pytest -q -m "not integration"`: 580 passed. Against the old `src/`, the 13 new tests
  fail.

## Leftovers
- Langfuse noise: experiments `infra-{before,after,final}-{regex,bm25}` (and their datasets'
  items are the existing dev items). Results files `results/infra-*` and
  `results/rescored/infra-*` (gitignored) can be deleted.
- `Runner.run` does not close the Redis client when it raises before its `try` (e.g. a
  Langfuse abort). This was already the case before; it is harmless in a CLI process.
