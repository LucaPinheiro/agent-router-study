"""Bedrock (Converse) twin of `openrouter.chat_json` for the dataset scripts: same body shape
(`model`, `messages`, `temperature`, `max_tokens`), JSON content, retries, a wall-clock deadline
and one spend-ledger row per call. Cost = tokens x `config/prices.yaml` (Bedrock reports no
cost). Phase 2 generates and audits on Bedrock: OpenRouter is reserved for Jev."""

from __future__ import annotations

import time
from typing import Any

from openrouter import ROOT, parse_json

# reasoning models spend their budget thinking unless told otherwise; the generator and the
# auditors answer a fixed JSON schema, where low effort is enough (as with OpenRouter in phase 1)
_REASONING_FIELDS: dict[str, dict[str, Any]] = {
    "openai.gpt-oss-": {"reasoning_effort": "low"},
}


def _price(model: str) -> Any:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from routing_study.budget import prices_for
    from routing_study.settings import Settings

    settings = Settings()
    price = prices_for(settings).get(("bedrock", model))
    if price is None:
        raise SystemExit(f"no bedrock price for {model!r} in {settings.budget.prices_path}")
    return price


def _client(region: str) -> Any:
    import boto3
    from botocore.config import Config

    cfg = Config(read_timeout=120, connect_timeout=10, retries={"max_attempts": 0})
    return boto3.client("bedrock-runtime", region_name=region, config=cfg)


def _converse_args(body: dict[str, Any]) -> dict[str, Any]:
    system = [{"text": m["content"]} for m in body["messages"] if m["role"] == "system"]
    messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in body["messages"]
        if m["role"] != "system"
    ]
    inference: dict[str, Any] = {"maxTokens": int(body.get("max_tokens") or 4096)}
    if body.get("temperature") is not None:
        inference["temperature"] = float(body["temperature"])
    args: dict[str, Any] = {
        "modelId": body["model"],
        "messages": messages,
        "inferenceConfig": inference,
    }
    if system:
        args["system"] = system
    extra = next((f for p, f in _REASONING_FIELDS.items() if body["model"].startswith(p)), None)
    if extra:
        args["additionalModelRequestFields"] = extra
    return args


def chat_json(
    body: dict[str, Any],
    *,
    purpose: str,
    led: Any = None,
    region: str = "sa-east-1",
    deadline_s: float = 180,
    attempts: int = 4,
) -> tuple[Any, dict[str, Any]]:
    """Converse call whose reply is JSON; returns (parsed, usage). Parsed is None after
    `attempts` failures. Reasoning text blocks are ignored: only the final text is parsed."""
    price = _price(body["model"])
    client = _client(region)
    args = _converse_args(body)
    usage: dict[str, Any] = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
    reserve = (4000 * price.input + args["inferenceConfig"]["maxTokens"] * price.output) / 1e6
    for attempt in range(attempts):
        try:
            if led is not None:
                led.check("bedrock", reserve, purpose)
            t0 = time.monotonic()
            r = client.converse(**args)
            wall = time.monotonic() - t0
            u = r.get("usage") or {}
            pt, ct = int(u.get("inputTokens") or 0), int(u.get("outputTokens") or 0)
            cost = (pt * price.input + ct * price.output) / 1e6
            usage["cost"] += cost
            usage["prompt_tokens"] += pt
            usage["completion_tokens"] += ct
            if led is not None:
                led.settle(
                    "bedrock",
                    0.0,
                    {
                        "model": body["model"],
                        "cost_usd": cost,
                        "prompt_tokens": pt,
                        "completion_tokens": ct,
                        "served_model": body["model"],
                        "wall_ms": round(wall * 1000, 1),
                        "purpose": purpose,
                    },
                )
            if wall > deadline_s:
                raise TimeoutError("wall-clock deadline")
            blocks = r["output"]["message"]["content"]
            text = "".join(b["text"] for b in blocks if "text" in b)
            return parse_json(text), usage
        except Exception as e:  # noqa: BLE001 - throttling, timeouts, bad JSON: retry
            name = type(e).__name__
            if name in ("AccessDeniedException", "UnrecognizedClientException"):
                raise SystemExit(f"Bedrock {name}: check AWS credentials/model access") from e
            print(f"  retry {attempt + 1}: {name} {str(e)[:120]}", flush=True)
            time.sleep(min(30, 2 ** (attempt + 1)))
    return None, usage
