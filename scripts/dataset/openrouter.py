"""Minimal OpenRouter chat client for the dataset scripts: JSON output, usage/cost capture,
wall-clock deadline, retries, and one spend-ledger row per call (`results/spend_ledger.jsonl`,
the same ledger `study budget` reads)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
API = "https://openrouter.ai/api/v1"


def ledger():  # noqa: ANN201
    sys.path.insert(0, str(ROOT / "src"))
    from routing_study.budget import ledger_for
    from routing_study.settings import Settings

    return ledger_for(Settings())


def credits(client: httpx.Client, key: str) -> dict[str, float]:
    """OpenRouter account totals (`total_credits`, `total_usage`); never logs the key."""
    r = client.get(f"{API}/credits", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    return {k: float(v) for k, v in r.json()["data"].items()}


def parse_json(text: str | None) -> Any:
    if not isinstance(text, str):
        raise ValueError("empty completion content")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    return json.loads(text)


def chat_json(
    client: httpx.Client,
    key: str,
    body: dict[str, Any],
    *,
    purpose: str,
    led: Any = None,
    deadline_s: float = 100,
    attempts: int = 4,
) -> tuple[Any, dict[str, Any]]:
    """POST a chat completion whose content is JSON; returns (parsed, usage). Parsed is None
    after `attempts` failures. 401/402/403 abort (bad key / no credits)."""
    body = {**body, "usage": {"include": True}}
    usage: dict[str, Any] = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
    for attempt in range(attempts):
        try:
            if led is not None:
                led.check("openrouter", 0.05, purpose)
            t0 = time.monotonic()
            chunks: list[bytes] = []
            with client.stream(
                "POST",
                f"{API}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=30,
            ) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes():
                    chunks.append(chunk)
                    if time.monotonic() - t0 > deadline_s:
                        raise httpx.ReadTimeout("wall-clock deadline")
            j = json.loads(b"".join(chunks))
            u = j.get("usage") or {}
            cost = float(u.get("cost") or 0.0)
            usage["cost"] += cost
            usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
            usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
            if led is not None:
                led.settle(
                    "openrouter",
                    0.0,
                    {
                        "model": body["model"],
                        "cost_usd": cost,
                        "prompt_tokens": int(u.get("prompt_tokens") or 0),
                        "completion_tokens": int(u.get("completion_tokens") or 0),
                        "served_model": j.get("model"),
                        "wall_ms": round((time.monotonic() - t0) * 1000, 1),
                        "purpose": purpose,
                    },
                )
            if "error" in j and "choices" not in j:
                raise ValueError(str(j["error"])[:200])
            return parse_json(j["choices"][0]["message"]["content"]), usage
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 402, 403):
                raise SystemExit(
                    f"OpenRouter HTTP {e.response.status_code}: check OPENROUTER_API_KEY/credits"
                ) from e
            print(f"  retry {attempt + 1}: HTTP {e.response.status_code}", flush=True)
            time.sleep(2**attempt)
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError, AttributeError) as e:
            print(f"  retry {attempt + 1}: {type(e).__name__}", flush=True)
            time.sleep(2**attempt)
    return None, usage
