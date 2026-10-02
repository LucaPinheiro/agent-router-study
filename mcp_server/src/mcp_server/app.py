"""FastAPI app: FastMCP streamable HTTP (stateless) at /mcp, /healthz, /readyz, bearer auth.

Run: uv run uvicorn mcp_server.app:app --port 8765
     CATALOG_PROFILE=large uv run uvicorn mcp_server.app:app --port 8766   # 62-tool catalog
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from mcp_server.server import TOOL_COUNTS, mcp, profile_from_env, profile_tools
from mcp_server.telemetry import setup_tracing

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")

# No default: a guessable shared token must never reach a listening server. Generate one with
# `python -c "import secrets; print(secrets.token_urlsafe(32))"` (see .env.example).
MCP_TOKEN = os.getenv("MCP_TOKEN", "")
MIN_TOKEN_LEN = 16
PROFILE = profile_from_env()


def check_token(token: str) -> None:
    if len(token) < MIN_TOKEN_LEN or token == "dev-token":
        raise RuntimeError(
            f"MCP_TOKEN must be set to a random secret of at least {MIN_TOKEN_LEN} characters"
        )


UNTRACED_PATHS = frozenset({"/healthz", "/readyz"})  # probes: no HTTP span, nothing exported


def untraced(scope: MutableMapping[str, Any]) -> bool:
    """FastAPI telemetry `exclude`: skip instrumentation of the health/readiness probes."""
    return scope.get("path") in UNTRACED_PATHS


mcp_app = mcp.http_app(path="/mcp", stateless_http=True, transport="http")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Exporter set up at server start, not on import (importing the app must not install a
    # process-global TracerProvider, e.g. in tests).
    check_token(MCP_TOKEN)  # refuse to start without a strong bearer token
    setup_tracing()
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(
    title="routing-study MCP server",
    lifespan=lifespan,
    # Export is owned by telemetry.setup_tracing (Langfuse auth); no env auto-exporters/metrics.
    # The HTTP span parents from the client's `traceparent` header (joins the turn trace).
    telemetry={
        "auto_configure": False,
        "metrics": False,
        "logs": False,
        "operation_spans": False,
        "exclude": untraced,
    },
)


@app.middleware("http")
async def bearer_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.url.path.startswith("/mcp"):
        auth = request.headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if (
            scheme.lower() != "bearer"
            or len(MCP_TOKEN) < MIN_TOKEN_LEN
            or not hmac.compare_digest(token, MCP_TOKEN)
        ):
            error = 'error="invalid_token"' if auth else ""
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f"Bearer {error}".strip()},
            )
    return await call_next(request)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    tools = len(profile_tools(PROFILE))
    ready = tools == TOOL_COUNTS[PROFILE]
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "tools": tools, "profile": PROFILE},
        status_code=200 if ready else 503,
    )


app.mount("/", mcp_app)
