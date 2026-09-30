"""FastMCP server: 18 tools, skill/policy resources, instructions, tracing middleware."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any

import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.resources import TextResource
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool, ToolResult
from opentelemetry import trace

from mcp_server.core import CUSTOMER_META_KEY, PKG_DIR, POLICIES, current_customer_id
from mcp_server.telemetry import TRACER_NAME, parent_context
from mcp_server.tools import REGISTRY

logger = logging.getLogger("mcp_server.calls")
SKILL_IDS = ("pedidos_logistica", "pagamentos_reembolsos", "trocas_devolucoes")
CUSTOMER_HEADER = "x-customer-id"


class CatalogMiddleware(Middleware):
    """Deterministic tools/list order; per-call customer binding and `mcp.tools/call` span."""

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        return sorted(await call_next(context), key=lambda t: t.name)

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        name = context.message.name
        fctx = context.fastmcp_context
        rctx = fctx.request_context if fctx is not None else None
        meta: dict[str, Any] = dict((rctx.meta if rctx else None) or context.message.meta or {})
        headers = get_http_headers()
        customer = headers.get(CUSTOMER_HEADER) or meta.get(CUSTOMER_META_KEY)
        token = current_customer_id.set(str(customer).strip().upper() if customer else None)
        tracer = trace.get_tracer(TRACER_NAME)
        start = time.perf_counter()
        try:
            with tracer.start_as_current_span(
                f"mcp.tools/call {name}",
                context=parent_context(headers, meta),
                kind=trace.SpanKind.SERVER,
                attributes={"mcp.method.name": "tools/call", "tool": name},
            ) as span:
                result = await call_next(context)
                sc = result.structured_content or {}
                status = sc.get("status", "error" if result.is_error else "completed")
                code = sc.get("code") or ""
                latency_ms = round((time.perf_counter() - start) * 1000, 3)
                span.set_attributes({"status": status, "code": code, "latency_ms": latency_ms})
                if result.is_error:
                    span.set_status(trace.StatusCode.ERROR, code or "tool error")
                logger.info(json.dumps({"event": "tools/call", "tool": name, "status": status,
                                        "code": code, "latency_ms": latency_ms}))
                return result
        finally:
            current_customer_id.reset(token)


def build_server() -> FastMCP:
    mcp = FastMCP(
        name="routing-study-pos-venda",
        instructions=(PKG_DIR / "instructions.md").read_text(encoding="utf-8"),
        version="0.1.0",
        middleware=[CatalogMiddleware()],
        dereference_schemas=False,  # keep shared $defs (Money, Address, OrderRef)
        cache_ttl=300,
        cache_scope="public",  # catalog, skills and policies do not vary by principal
    )
    for tool in REGISTRY:
        mcp.add_tool(tool)

    for skill_id in SKILL_IDS:
        mcp.add_resource(
            TextResource(
                uri=f"skill://{skill_id}/SKILL.md",
                name=f"skill_{skill_id}",
                title=f"Skill {skill_id}",
                description=f"Playbook da skill {skill_id} (frontmatter + cenários).",
                mime_type="text/markdown",
                text=(PKG_DIR / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8"),
            )
        )
    mcp.add_resource(
        TextResource(
            uri="shop://policies",
            name="policies",
            title="Políticas da loja",
            description="Prazos de troca, devolução, reembolso, garantia, SLAs e fora de escopo.",
            mime_type="application/json",
            text=json.dumps(POLICIES, ensure_ascii=False, indent=1),
        )
    )
    return mcp


mcp = build_server()
