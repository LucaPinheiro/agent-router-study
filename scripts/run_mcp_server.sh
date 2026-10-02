#!/usr/bin/env bash
# Run the MCP server locally (outside docker) for one catalog profile.
#   scripts/run_mcp_server.sh          # small (phase-1 catalog, 18 tools) on :8765
#   scripts/run_mcp_server.sh large    # large (phase-2 catalog, 62 tools) on :8766
# Docker: `make up-app` starts both (services mcp-server and mcp-server-large).
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE="${1:-small}"
case "$PROFILE" in
  small) PORT=8765 ;;
  large) PORT=8766 ;;
  *) echo "usage: $0 [small|large]" >&2; exit 2 ;;
esac
set -a; [[ -f .env ]] && source .env; set +a
exec env CATALOG_PROFILE="$PROFILE" uv run uvicorn mcp_server.app:app --host 127.0.0.1 --port "$PORT"
