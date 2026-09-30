"""S0 spike: verify Langfuse SDK v4 tracing shape against local Langfuse.

Run: uv run --with langchain python spikes/langfuse_spike.py
(`langchain` is required by langfuse.langchain.CallbackHandler; not yet a project dep.)
"""

import os
import time
import uuid

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from opentelemetry import propagate

from langfuse import get_client, observe
from langfuse.langchain import CallbackHandler

load_dotenv()
HOST = os.environ["LANGFUSE_HOST"]
AUTH = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
lf = get_client()
assert lf.auth_check(), "langfuse auth failed"


class CostCallbackHandler(CallbackHandler):
    """Langfuse's handler ignores OpenRouter's `usage.cost`; inject it as cost_details.

    Relies on the private `_runs` map (run_id -> open observation). Pin langfuse and re-run this spike on upgrade.
    """

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        try:
            usage = (response.llm_output or {}).get("token_usage") or {}
            cost = usage.get("cost")
            if cost is not None and (gen := self._runs.get(run_id)) is not None:
                gen.update(cost_details={"total": float(cost)})
        finally:
            return super().on_llm_end(response, run_id=run_id, parent_run_id=parent_run_id, **kwargs)


@observe(name="route.skill.regex")  # decorator-style router step, nests under current span
def fake_router(text: str) -> dict:
    return {"choice": "pedidos_logistica", "confidence": 0.9}


run_tag = uuid.uuid4().hex[:8]
with lf.start_as_current_observation(name="turn", as_type="span", input="onde esta meu pedido?") as root:
    trace_id = lf.get_current_trace_id()
    root.update(metadata={"spike_run": run_tag})

    fake_router("onde esta meu pedido?")

    # (a) manual generation with explicit cost
    with lf.start_as_current_observation(
        name="manual-generation",
        as_type="generation",
        model="fake-model",
        usage_details={"input": 10, "output": 5},
        cost_details={"total": 0.0012},
    ) as gen:
        gen.update(output="ok")

    # (b) real LLM call through OpenRouter, nested via the LangChain CallbackHandler
    llm = ChatOpenAI(
        model="anthropic/claude-haiku-4.5",
        base_url=os.environ["OPENROUTER_BASE_URL"],
        api_key=os.environ["OPENROUTER_API_KEY"],
        extra_body={"usage": {"include": True}},
        max_tokens=30,
    )
    resp = llm.invoke("Diga 'oi' em uma palavra.", config={"callbacks": [CostCallbackHandler()]})
    print("response_metadata.token_usage:", resp.response_metadata.get("token_usage"))
    print("usage_metadata:", resp.usage_metadata)

    # traceparent for a remote service (what the MCP client would put in _meta)
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    print("traceparent:", carrier.get("traceparent"))

    # (c) score on the trace
    lf.create_score(trace_id=trace_id, name="spike_score", value=1.0, data_type="NUMERIC", comment="spike")

# (d) datasets: v4 has no item.run(); link a manual trace via api.dataset_run_items.create
ds_name = f"spike-{run_tag}"
lf.create_dataset(name=ds_name)
lf.create_dataset_item(dataset_name=ds_name, input={"q": "oi"}, expected_output={"skill": "x"})
item = lf.get_dataset(ds_name).items[0]
with lf.start_as_current_observation(name="turn", as_type="span", input=item.input) as ds_span:
    ds_trace_id = lf.get_current_trace_id()
    dri = lf.api.dataset_run_items.create(
        run_name="spike-run", dataset_item_id=item.id, trace_id=ds_trace_id, observation_id=ds_span.id
    )
    print("dataset_run_id:", dri.dataset_run_id)
    ds_span.update(output="done")
    lf.score_current_trace(name="ds_score", value=1.0)

lf.flush()


def fetch(path: str, params: dict | None = None) -> dict:
    r = None
    for _ in range(30):
        r = httpx.get(f"{HOST}{path}", auth=AUTH, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
        time.sleep(2)
    raise RuntimeError(f"{path} -> {r.status_code} {r.text[:200]}")


# Langfuse v4 server (events_only mode): /api/public/traces/{id} is NOT available.
# Use v2 observations + v2 scores, filtered by traceId.
FIELDS = "core,basic,model,usage,io"


def wait_trace(tid: str, n_obs: int, n_scores: int) -> tuple[list[dict], list[dict]]:
    for _ in range(30):
        obs = fetch("/api/public/v2/observations", {"traceId": tid, "fields": FIELDS, "limit": 100})["data"]
        scores = fetch("/api/public/v3/scores", {"traceId": tid, "fields": "core,subject"})["data"]
        if len(obs) >= n_obs and len(scores) >= n_scores:
            break
        time.sleep(2)
    return obs, scores


obs, scores = wait_trace(trace_id, 4, 1)
print(f"\ntrace {trace_id} scores={[(s['name'], s['value']) for s in scores]}")
by_parent: dict = {}
for o in obs:
    by_parent.setdefault(o.get("parentObservationId"), []).append(o)


def show(pid: str | None, depth: int = 0) -> None:
    for o in sorted(by_parent.get(pid, []), key=lambda x: x["startTime"]):
        print(f"{'  ' * depth}- {o['name']} [{o['type']}] id={o['id'][:8]} parent={(pid or '-')[:8]} "
              f"model={o.get('providedModelName') or o.get('model')} usage={o.get('usageDetails')} "
              f"cost_details={o.get('costDetails')} total_cost={o.get('totalCost')}")
        show(o["id"], depth + 1)


show(None)
print("keys of one observation:", sorted(obs[0].keys()))
ds_obs, ds_scores = wait_trace(ds_trace_id, 1, 1)
print(f"\ndataset-run trace {ds_trace_id}: obs={[o['name'] for o in ds_obs]} scores={[s['name'] for s in ds_scores]}")
try:  # dataset-run listing may be unavailable on v4 events_only servers
    runs = lf.api.datasets.get_runs(dataset_name=ds_name)
    print("dataset runs:", [r.name for r in runs.data])
except Exception as e:  # noqa: BLE001
    print("dataset runs query unavailable:", type(e).__name__, str(e)[:120])
