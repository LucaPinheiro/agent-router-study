"""Export the server's tools/list result to mcp_server/tools_list.json (input of the linter).

Run: uv run python -m mcp_server.export
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from fastmcp import Client

from mcp_server.server import mcp

OUT = Path(__file__).resolve().parents[2] / "tools_list.json"


async def tools_list_payload(client: Client) -> dict[str, Any]:
    result = await client.list_tools_mcp()
    return result.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _export() -> dict[str, Any]:
    async with Client(mcp) as client:
        return await tools_list_payload(client)


def main() -> None:
    data = asyncio.run(_export())
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(data['tools'])} tools)")


if __name__ == "__main__":
    main()
