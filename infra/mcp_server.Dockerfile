# MCP server (FastAPI + FastMCP). Build context: repo root (uv workspace).
#   docker build -f infra/mcp_server.Dockerfile -t routing-study-mcp .
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies only (cached layer): workspace metadata + lockfile.
COPY pyproject.toml uv.lock ./
COPY mcp_server/pyproject.toml mcp_server/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package mcp-server --no-install-workspace

# Server source (mock data, skills, policies and instructions live inside the package).
COPY mcp_server/src mcp_server/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package mcp-server

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8765
CMD ["uvicorn", "mcp_server.app:app", "--host", "0.0.0.0", "--port", "8765"]
