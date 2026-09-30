"""Langfuse v4 helpers: no-op-safe spans, turn root, traceparent, and API read-back.

Verified API: spikes/LANGFUSE_V4_API.md. The server runs in events_only mode, so traces are read
back through /api/public/v2/observations and /api/public/v3/scores.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import httpx
from opentelemetry import propagate

from routing_study.routers.common import tracing_active


class _NoopSpan:
    id: str | None = None

    def update(self, **_: Any) -> None:
        pass


# MCP client instrumentation scopes. Langfuse's default filter drops them, but the
# `MCP send tools/call` span is the parent the server's `mcp.tools/call` span points to (the MCP
# SDK injects its own span into `_meta.traceparent`), so dropping it orphans the server subtree.
MCP_CLIENT_SCOPES = frozenset({"mcp-python-sdk", "fastmcp"})
_initialized = False


def _export_span(span: Any) -> bool:
    from langfuse.span_filter import is_default_export_span

    if is_default_export_span(span):
        return True
    scope = span.instrumentation_scope.name if span.instrumentation_scope else ""
    # only inside a trace we own (catalog fetches outside a turn would be orphan traces)
    return scope in MCP_CLIENT_SCOPES and span.parent is not None


def enabled() -> bool:
    return tracing_active()


def init() -> None:
    """Create the process-wide Langfuse client with the MCP-aware export filter. Must run before
    any `get_client()` (the first client per public key wins)."""
    global _initialized
    if _initialized or not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    from langfuse import Langfuse

    Langfuse(should_export_span=_export_span)
    _initialized = True


def client() -> Any:
    from langfuse import get_client

    init()
    return get_client()


def register_prompts(texts: Mapping[str, str]) -> dict[str, int]:
    """Langfuse Prompt Management (plan §4.4): one version per prompt content, labelled with its
    hash; created on first use. Returns name -> version ({} without Langfuse)."""
    if not enabled():
        return {}
    from langfuse.api import NotFoundError

    lf, out = client(), {}
    for name, text in texts.items():
        label = hashlib.sha256(text.encode()).hexdigest()[:12]
        try:
            prompt = lf.get_prompt(name, label=label, cache_ttl_seconds=0, max_retries=0)
        except NotFoundError:
            prompt = lf.create_prompt(name=name, prompt=text, labels=[label])
        out[name] = prompt.version
    return out


@contextmanager
def span(name: str, *, as_type: str = "span", **kwargs: Any) -> Iterator[Any]:
    """Current-context observation (children nest under it); a no-op without Langfuse."""
    if not enabled():
        yield _NoopSpan()
        return
    with client().start_as_current_observation(name=name, as_type=as_type, **kwargs) as obs:
        yield obs


@contextmanager
def turn(*, session_id: str, tags: list[str], metadata: Mapping[str, str],
         input: Any) -> Iterator[tuple[Any, str | None]]:
    """Root `turn` span with trace attributes propagated to every child. Yields (span, trace_id)."""
    if not enabled():
        yield _NoopSpan(), None
        return
    from langfuse import propagate_attributes

    lf = client()
    with (
        propagate_attributes(session_id=session_id, tags=tags,
                             metadata={k: str(v) for k, v in metadata.items()},
                             trace_name="turn"),
        lf.start_as_current_observation(name="turn", as_type="span", input=input) as root,
    ):
        yield root, lf.get_current_trace_id()


def traceparent() -> dict[str, str]:
    """W3C context of the current span, for MCP `_meta` (the server nests its span under it)."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


def flush() -> None:
    if enabled():
        client().flush()


# ---------------------------------------------------------------- read-back (public API)


class LangfuseAPI:
    def __init__(self, host: str | None = None, public_key: str | None = None,
                 secret_key: str | None = None) -> None:
        self.host = (host or os.environ["LANGFUSE_HOST"]).rstrip("/")
        self.auth = (public_key or os.environ["LANGFUSE_PUBLIC_KEY"],
                     secret_key or os.environ["LANGFUSE_SECRET_KEY"])

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        r = httpx.get(f"{self.host}{path}", auth=self.auth, params=params, timeout=15)
        r.raise_for_status()
        return r.json()["data"]

    def observations(self, trace_id: str) -> list[dict[str, Any]]:
        return self._get("/api/public/v2/observations", {
            "traceId": trace_id, "fields": "core,basic,model,usage,io,metadata", "limit": 100})

    def scores(self, trace_id: str) -> list[dict[str, Any]]:
        return self._get("/api/public/v3/scores", {"traceId": trace_id, "fields": "core,subject"})

    def wait(self, trace_id: str, *, min_obs: int = 1, scores: set[str] | None = None,
             timeout_s: float = 60.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Poll until >= min_obs observations and all named scores are visible (async ingest)."""
        deadline = time.monotonic() + timeout_s
        obs: list[dict[str, Any]] = []
        sc: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            obs, sc = self.observations(trace_id), self.scores(trace_id)
            if len(obs) >= min_obs and (scores or set()) <= {s["name"] for s in sc}:
                break
            time.sleep(2)
        return obs, sc


def format_tree(observations: list[dict[str, Any]]) -> str:
    children: dict[str | None, list[dict[str, Any]]] = {}
    ids = {o["id"] for o in observations}
    for o in observations:
        parent = o.get("parentObservationId")
        children.setdefault(parent if parent in ids else None, []).append(o)
    lines: list[str] = []

    def walk(pid: str | None, depth: int) -> None:
        for o in sorted(children.get(pid, []), key=lambda x: x["startTime"]):
            extra = ""
            if o.get("type") == "GENERATION":
                extra = (f" model={o.get('providedModelName') or o.get('model')}"
                         f" cost={o.get('totalCost')}")
            lines.append(f"{'  ' * depth}- {o['name']} [{o['type']}]{extra}")
            walk(o["id"], depth + 1)

    walk(None, 0)
    return "\n".join(lines)
