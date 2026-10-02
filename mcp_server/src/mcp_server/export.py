"""Export the server's tools/list result (input of the linter and of the catalog hash lock).

Run: uv run python -m mcp_server.export            # small -> mcp_server/tools_list.json
     uv run python -m mcp_server.export large      # large -> mcp_server/tools_list_large.json
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from fastmcp import Client

from mcp_server.server import build_server

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tools_list.json"
OUTS = {"small": OUT, "large": ROOT / "tools_list_large.json"}


async def tools_list_payload(client: Client) -> dict[str, Any]:
    result = await client.list_tools_mcp()
    return result.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _export(profile: str) -> dict[str, Any]:
    async with Client(build_server(profile)) as client:
        return await tools_list_payload(client)


def main() -> None:
    profile = sys.argv[1] if len(sys.argv) > 1 else "small"
    data = asyncio.run(_export(profile))
    out = OUTS[profile]
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(data['tools'])} tools)")


if __name__ == "__main__":
    main()
