"""Catalog identity, Redis cache round-trip, route options and McpTools error handling."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import mcp.types as mt
import pytest
from mcp.shared.exceptions import MCPError

from routing_study import catalog as catalog_mod
from routing_study.catalog import Catalog, CatalogProvider, McpTools, Skill
from routing_study.prompts import system_blocks
from routing_study.settings import Settings

sys.path.insert(0, str(Path(__file__).parent / "graph"))
from graph_fakes import make_catalog  # noqa: E402


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.data[key], self.ttls[key] = value, ex

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)


def _unsorted_catalog() -> Catalog:
    """Server order that is NOT alphabetical: skills pedidos, pagamentos; properties z, a."""
    cat = make_catalog()
    skills = dict(cat.skills)
    tools = [
        dict(
            t,
            inputSchema={
                "type": "object",
                "properties": {"zeta": {"type": "string"}, "alpha": {"type": "string"}},
            },
        )
        for t in cat.tools
    ]
    return Catalog(
        url=cat.url,
        protocol_version=cat.protocol_version,
        instructions=cat.instructions,
        tools=tools,
        skills=skills,
    )


def _prompt(cat: Catalog) -> str:
    blocks = system_blocks(cat, native=True, skill=None, customer=None)
    return "".join(b["text"] for b in blocks) + repr(
        [cat.openai_tool(t["name"]) for t in cat.tools]
    )


async def test_redis_round_trip_preserves_server_order_and_prompt_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served = _unsorted_catalog()
    assert list(served.skills) != sorted(served.skills)

    async def fetch(_: Settings) -> Catalog:
        return served

    monkeypatch.setattr(catalog_mod, "fetch_catalog", fetch)
    redis = FakeRedis()
    settings = Settings(_env_file=None)
    first, src1 = await CatalogProvider(settings, redis).get()
    cached, src2 = await CatalogProvider(settings, redis).get()  # new process: from Redis
    assert (src1, src2) == ("server", "redis")
    assert list(cached.skills) == list(served.skills)
    assert [o.id for o in cached.skill_options()] == [o.id for o in served.skill_options()]
    assert list(cached.openai_tool("cancel_order")["function"]["parameters"]["properties"]) == [
        "zeta",
        "alpha",
    ]
    assert _prompt(cached) == _prompt(served)
    assert cached.hash == served.hash


def test_catalog_hash_includes_order() -> None:
    cat = make_catalog()
    reordered = Catalog(
        url=cat.url,
        protocol_version=cat.protocol_version,
        instructions=cat.instructions,
        tools=cat.tools,
        skills=dict(reversed(list(cat.skills.items()))),
    )
    assert reordered.hash != cat.hash


async def test_memo_from_redis_expires_with_the_redis_key(monkeypatch: pytest.MonkeyPatch) -> None:
    served = make_catalog()
    redis = FakeRedis()
    redis.data["k"], redis.ttls["k"] = served.to_json(), 5  # key written 295 s ago
    provider = CatalogProvider(Settings(_env_file=None), redis)
    provider.key = "k"
    now = [1000.0]
    monkeypatch.setattr(catalog_mod.time, "monotonic", lambda: now[0])
    assert (await provider.get())[1] == "redis"
    now[0] += 4
    assert (await provider.get())[1] == "memory"
    now[0] += 2  # Redis key expired: the memo must not outlive it
    redis.data.clear()

    async def fetch(_: Settings) -> Catalog:
        return served

    monkeypatch.setattr(catalog_mod, "fetch_catalog", fetch)
    assert (await provider.get())[1] == "server"


def test_skill_dataclass_round_trip() -> None:
    cat = make_catalog()
    assert Catalog.from_json(cat.to_json()).skills["pedidos_logistica"] == Skill(
        **vars(cat.skills["pedidos_logistica"])
    )


def test_tool_route_options_drop_sibling_sections_but_executor_sees_all() -> None:
    desc = (
        'Cancela um pedido não enviado.\nWHEN TO USE: "quero cancelar".\n'
        "DON'T USE FOR: pedido entregue (use create_return_request).\n"
        "PARAMETERS: order_id opcional.\nCONFIRMATION: não requer.\n"
        "RESULT: protocolo; repasse sem alterar."
    )
    cat = make_catalog()
    tools = [dict(t, description=desc) if t["name"] == "cancel_order" else t for t in cat.tools]
    cat = Catalog(
        url=cat.url,
        protocol_version=cat.protocol_version,
        instructions=cat.instructions,
        tools=tools,
        skills=cat.skills,
    )
    opt = next(o for o in cat.tool_options("pedidos_logistica") if o.id == "cancel_order")
    assert opt.description == (
        'Cancela um pedido não enviado.\nWHEN TO USE: "quero cancelar".'
        "\nPARAMETERS: order_id opcional."
    )
    assert "create_return_request" not in opt.description
    assert cat.openai_tool("cancel_order")["function"]["description"] == desc


class _RaisingClient:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def call_tool_mcp(self, *_: object, **__: object) -> None:
        raise self.exc


def _tools(exc: BaseException) -> McpTools:
    tools = McpTools(Settings(_env_file=None), "C001")
    tools._client = _RaisingClient(exc)  # type: ignore[assignment]
    return tools


async def test_invalid_params_is_a_tool_visible_error() -> None:
    out = await _tools(MCPError(mt.INVALID_PARAMS, "order_id: wrong type")).call("x", {})
    assert out.is_error and out.structured == {"status": "error", "code": "PROTOCOL_ERROR"}
    assert "order_id: wrong type" in out.text


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("refused"),
        MCPError(mt.CONNECTION_CLOSED, "Connection closed"),
        MCPError(mt.REQUEST_TIMEOUT, "timed out"),
        MCPError(mt.INTERNAL_ERROR, "Server returned an error response"),
        MCPError(mt.INVALID_REQUEST, "Session terminated"),
        RuntimeError("Client is not connected"),
    ],
)
async def test_transport_and_session_errors_raise(exc: BaseException) -> None:
    with pytest.raises(type(exc)):
        await _tools(exc).call("x", {})
