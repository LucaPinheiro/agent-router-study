from collections.abc import AsyncIterator

import pytest
from fastmcp import Client
from mcp_server.server import mcp


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(mcp) as c:
        yield c
