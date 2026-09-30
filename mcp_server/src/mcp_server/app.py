"""FastAPI app: FastMCP streamable HTTP (stateless) at /mcp, /healthz, /readyz, bearer auth.

Run: uv run uvicorn mcp_server.app:app --port 8765
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from mcp_server.core import REGISTRY
from mcp_server.server import mcp
from mcp_server.telemetry import setup_tracing

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
setup_tracing()

MCP_TOKEN = os.getenv("MCP_TOKEN", "dev-token")
mcp_app = mcp.http_app(path="/mcp", stateless_http=True, transport="http")
app = FastAPI(
    title="routing-study MCP server",
    lifespan=mcp_app.lifespan,
    # Export is owned by telemetry.setup_tracing (Langfuse auth); no env auto-exporters/metrics.
    telemetry={"auto_configure": False, "metrics": False, "logs": False, "operation_spans": False},
)


@app.middleware("http")
async def bearer_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.url.path.startswith("/mcp"):
        auth = request.headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token, MCP_TOKEN):
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
    ready = len(REGISTRY) == 18
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "tools": len(REGISTRY)},
        status_code=200 if ready else 503,
    )


app.mount("/", mcp_app)
