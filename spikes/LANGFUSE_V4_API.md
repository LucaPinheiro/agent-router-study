# Langfuse Python SDK 4.15.6 vs self-hosted server 4.47.0 (verified by `spikes/langfuse_spike.py`)

Local server: `http://localhost:3300` (3000 and 3100 are taken by grafana/loki on this machine), keys `pk-lf-local` / `sk-lf-local`
(env: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`). `get_client()` reads them from the process env only, so call `load_dotenv()` first.

## Gotchas
- `from langfuse.langchain import CallbackHandler` needs the top-level **`langchain`** package. It is not a project dep yet. The spike runs with `uv run --with langchain`.
- The SDK has **no** `langfuse.decorators`, `langfuse.trace()` or `item.run()`. It has no `lf.trace()` / `lf.span()` / `lf.generation()` either.
- The v4 server runs in *events_only* mode. Legacy REST endpoints return 404: `/api/public/traces[/{id}]`, `/v2/scores`, `/datasets/{name}/runs`, `dataset-run-items` list.
  Read data back with `GET /api/public/v2/observations?traceId=<id>&fields=core,basic,model,usage,io&limit=100` (Basic auth pk:sk) and `GET /api/public/v3/scores?traceId=<id>&fields=core,subject`.
- Ingestion is asynchronous. Poll for about 10 s after `flush()` until all expected observations and scores are visible.
- Score responses return the trace id under `subject.id`, not `traceId`.
- Observation response fields: `id, traceId, parentObservationId, type` (SPAN | GENERATION | ...), `name, model, usageDetails, costDetails, totalCost, startTime, latency`.

## Imports
```python
from langfuse import get_client, observe, propagate_attributes
from langfuse.langchain import CallbackHandler
lf = get_client()          # singleton; lf.auth_check() -> bool
```

## Spans and generations (context managers set the OTel current context, so children nest automatically)
```python
with lf.start_as_current_observation(name="turn", as_type="span", input=..., metadata={...}) as root:
    trace_id = lf.get_current_trace_id()        # 32-hex
    root.id                                     # 16-hex span id
    with lf.start_as_current_observation(
        name="gen", as_type="generation", model="m",
        usage_details={"input": 10, "output": 5}, cost_details={"total": 0.0012},
    ) as gen:
        gen.update(output="...")                # also gen.update(cost_details=..., usage_details=..., metadata=...)
    with root.start_as_current_observation(name="child", as_type="tool"): ...   # explicit parent also works
lf.update_current_span(...); lf.update_current_generation(...)   # act on the current observation
```
`as_type`: span, generation, embedding, agent, tool, chain, retriever, evaluator, guardrail.
Non-context version: `obs = lf.start_observation(name=..., as_type=...)` and then `obs.end()`. It is not made current.
Decorator: `@observe(name="route.skill.regex")` works on sync and async functions. It nests under the current span, and captures args and return value as input and output.

Trace-level attributes (session, tags, user, trace metadata) propagate to all children created inside the block:
```python
with propagate_attributes(session_id=case_id, tags=[exp_id, cfg], metadata={"git_sha": "..."}):
    ...
```
Check the signature (`inspect.signature(propagate_attributes)`) before use. Metadata values must be strings.

## Cost with OpenRouter
- Send `extra_body={"usage": {"include": True}}` to ChatOpenAI.
- The cost then arrives in `resp.response_metadata["token_usage"]["cost"]` (USD float). `usage_metadata` has only tokens.
- The stock `CallbackHandler` records tokens but **not** that cost. Langfuse cannot infer it either, because `anthropic/claude-haiku-4.5` is not in its price table, so `totalCost` is None.
- The spike's `CostCallbackHandler(CallbackHandler)` overrides `on_llm_end`. It calls `self._runs.get(run_id).update(cost_details={"total": cost})` and then `super()`. Result: the `ChatOpenAI` generation has `cost_details={'total': 4.9e-05}` and `totalCost=4.9e-05`. This relies on the private `_runs`, so keep langfuse pinned.

## CallbackHandler nesting
```python
with lf.start_as_current_observation(name="turn"):
    graph.invoke(state, config={"callbacks": [CostCallbackHandler()]})   # one handler per invocation
```
The LangChain/LangGraph runs become children of the current span, so the tree is turn -> ChatOpenAI generation. No `trace_context` is needed.
Verified: the `ChatOpenAI` generation is a child of `turn` next to the `@observe` and manual siblings.

## Trace context propagation to a remote HTTP/MCP service
Client side, inside the span:
```python
from opentelemetry import propagate
carrier: dict[str, str] = {}
propagate.inject(carrier)          # carrier["traceparent"] == "00-<trace_id>-<span_id>-01"
# send in an HTTP header `traceparent`, or MCP request `_meta = {"traceparent": ...}`
```
Server side, either way makes the span a child of the client's span in the same trace (both verified):
```python
# a) OTel-native
ctx = propagate.extract({"traceparent": tp}); tok = context.attach(ctx)
with lf.start_as_current_observation(name="mcp.tools/call x"): ...
context.detach(tok)
# b) Langfuse-native (trace_id = tp.split("-")[1], parent = tp.split("-")[2])
with lf.start_as_current_observation(name="...", trace_context={"trace_id": tid, "parent_span_id": sid}): ...
```
Alternative for a server with a plain OTel SDK: OTLP/HTTP to `http://localhost:3300/api/public/otel` with headers
`Authorization: Basic base64(pk:sk)` and `x-langfuse-ingestion-version: 4`.
A separate process with its own `get_client()` must call `lf.flush()` before exit.

## Scores
```python
lf.create_score(trace_id=tid, name="skill_correct", value=1.0, data_type="NUMERIC"|"BOOLEAN"|"CATEGORICAL", comment=..., observation_id=None)
lf.score_current_trace(name=..., value=...)     # inside a span; also score_current_span
```
For a CATEGORICAL score, pass a str value (e.g. `resolved_by`).

## Datasets and run linking
```python
lf.create_dataset(name=ds); lf.create_dataset_item(dataset_name=ds, input=..., expected_output=..., metadata=..., id=optional)
items = lf.get_dataset(ds).items                # DatasetItem: .id .input .expected_output .metadata
with lf.start_as_current_observation(name="turn", input=item.input) as root:
    lf.api.dataset_run_items.create(run_name=config_name, dataset_item_id=item.id,
                                    trace_id=lf.get_current_trace_id(), observation_id=root.id)   # returns .dataset_run_id
    ...
```
`lf.run_experiment(name=, run_name=, data=ds.items, task=fn(item, **kw), evaluators=[...])` is the high-level alternative. It creates its own `experiment-item-run` root span.
Not verified: reading dataset runs back over the API (those endpoints 404 in events_only mode). The `create` call succeeds and returns a `dataset_run_id`.

## Flush
`lf.flush()` blocks until the span exporter and score queue are drained. Call it at the end of the CLI or test. `lf.shutdown()` also flushes.
