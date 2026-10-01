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


# ---------------------------------------------------------------- F8: rendered P1 guide


def _live_guide(level: str, options: list, skill: str | None = None) -> str:
    from routing_study.prompts.routers import parse_variant
    from routing_study.routers.base import RoutingInput
    from routing_study.routers.llm import build_messages

    inp = RoutingInput(message="oi", level=level, loaded_skill=skill)  # type: ignore[arg-type]
    msgs = build_messages(
        inp,
        options,
        history_turns=0,
        allow_abstain=False,
        json_reply=False,
        spec=parse_variant("P0+P1"),
    )
    content = msgs[0].content
    system = content if isinstance(content, str) else content[0]["text"]
    return system.split("<guide>")[1].split("</guide>")[0]


@pytest.fixture(scope="module")
async def live_catalog() -> Catalog:
    from fastmcp import Client
    from mcp_server.server import mcp

    return await catalog_mod.fetch_catalog(
        Settings(_env_file=None), Client(mcp, mode=catalog_mod.PROTOCOL_VERSION)
    )


async def test_p1_skill_guide_keeps_only_skill_level_subjects(live_catalog: Catalog) -> None:
    guide = _live_guide("skill", live_catalog.skill_options())
    lines = [ln for ln in guide.splitlines() if ln.startswith("- not ")]
    # order-state preconditions of one tool's action are not skill-level facts
    for false in (
        "- not pedidos_logistica: pedido já entregue",
        "- not pedidos_logistica: se o pedido já foi entregue",
        "pedido já enviado (use __global__)",
        "- not pagamentos_reembolsos: pedido ainda não enviado",
        "- not pagamentos_reembolsos: se o pedido ainda não foi enviado",
        "- not trocas_devolucoes: pedido não entregue",
        "- not trocas_devolucoes: pedido não enviado",
        "- not trocas_devolucoes: pedido extraviado",
        "- not trocas_devolucoes: se o pedido",
        # mixed clause: request_refund (same skill) is one of its targets
        "- not pagamentos_reembolsos: desistência ou devolução",
    ):
        assert false not in guide, false
    # a skill is never told to avoid a clause pointing (also) to itself
    for ln in lines:
        home = ln.removeprefix("- not ").split(":", 1)[0]
        assert f"use {home}" not in ln and f"/ {home}" not in ln, ln
    for true in (
        "- not pedidos_logistica: dinheiro de volta de pedido já cancelado ou extraviado "
        "(use pagamentos_reembolsos)",
        "- not pedidos_logistica: cobrança não reconhecida (use pagamentos_reembolsos)",
        "- not pagamentos_reembolsos: status do pedido (use pedidos_logistica)",
        "- not pagamentos_reembolsos: produto recebido a devolver (use trocas_devolucoes)",
        "- not trocas_devolucoes: rastrear a entrega de um pedido (use pedidos_logistica)",
        "- not __global__: rastreio (use pedidos_logistica)",
    ):
        assert true in guide, true


async def test_p1_tool_guide_keeps_tool_level_preconditions(live_catalog: Catalog) -> None:
    trocas = _live_guide(
        "tool", live_catalog.tool_options("trocas_devolucoes"), "trocas_devolucoes"
    )
    assert "- not create_exchange: dinheiro de volta (use create_return_request)" in trocas
    assert "- not create_return_request: trocar tamanho ou cor (use create_exchange)" in trocas
    pedidos = _live_guide(
        "tool", live_catalog.tool_options("pedidos_logistica"), "pedidos_logistica"
    )
    # the precondition stays where it is true: between two tools of the option set
    assert (
        "- not update_delivery_address: se o pedido já foi enviado (use escalate_to_human)"
        in pedidos
    )
    assert "- not reschedule_delivery: desistir do pedido (use cancel_order)" in pedidos
    pagamentos = _live_guide(
        "tool", live_catalog.tool_options("pagamentos_reembolsos"), "pagamentos_reembolsos"
    )
    assert (
        "- not dispute_charge: desistência ou devolução "
        "(use cancel_order, request_refund ou create_return_request)" in pagamentos
    )


# ---------------------------------------------------------------- protocol pin / content hash


def _variant(cat: Catalog, **changes: object) -> Catalog:
    fields = {
        "url": cat.url,
        "protocol_version": cat.protocol_version,
        "instructions": cat.instructions,
        "tools": cat.tools,
        "skills": cat.skills,
        "ttl_s": cat.ttl_s,
    }
    return Catalog(**(fields | changes))  # type: ignore[arg-type]


def _reorder_schema_keys(tool: dict) -> dict:
    """What a 2025-11-25 fetch returns: same tool, JSON-object keys in another order."""
    schema = dict(reversed(list(tool["inputSchema"].items())))
    return dict(reversed(list({**tool, "inputSchema": schema}.items())))


def test_catalog_hash_is_content_only() -> None:
    cat = _unsorted_catalog()
    legacy = _variant(
        cat,
        protocol_version="2025-11-25",
        url="http://elsewhere/mcp",
        ttl_s=17,
        tools=[_reorder_schema_keys(t) for t in cat.tools],
    )
    assert legacy.to_json() != cat.to_json()
    assert legacy.hash == cat.hash


def test_catalog_hash_follows_semantic_changes() -> None:
    cat = _unsorted_catalog()
    first = cat.tools[0]
    changed = {
        "instructions": _variant(cat, instructions="OTHER"),
        "description": _variant(cat, tools=[{**first, "description": "x"}, *cat.tools[1:]]),
        "tool order": _variant(cat, tools=list(reversed(cat.tools))),
        "properties order": _variant(
            cat,
            tools=[
                {
                    **first,
                    "inputSchema": {
                        "type": "object",
                        "properties": {"alpha": {"type": "string"}, "zeta": {"type": "string"}},
                    },
                },
                *cat.tools[1:],
            ],
        ),
        "skill markdown": _variant(
            cat,
            skills={
                k: Skill(s.id, s.description, s.examples, s.markdown + "!")
                for k, s in cat.skills.items()
            },
        ),
    }
    for what, other in changed.items():
        assert other.hash != cat.hash, what


def test_mcp_clients_are_pinned_to_2026_07_28() -> None:
    assert catalog_mod.PROTOCOL_VERSION == "2026-07-28"
    settings = Settings(_env_file=None)
    assert catalog_mod.mcp_client(settings).mode == "2026-07-28"
    assert catalog_mod.mcp_client(settings, "C001").mode == "2026-07-28"
    assert CatalogProvider(settings).key.endswith(":2026-07-28")


async def test_redis_entry_of_another_protocol_is_never_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served = make_catalog()
    stale = _variant(served, protocol_version="2025-11-25")
    redis = FakeRedis()
    provider = CatalogProvider(Settings(_env_file=None), redis)
    redis.data[provider.key], redis.ttls[provider.key] = stale.to_json(), 200

    async def fetch(_: Settings) -> Catalog:
        return served

    monkeypatch.setattr(catalog_mod, "fetch_catalog", fetch)
    got, source = await provider.get()
    assert (source, got.protocol_version) == ("server", "2026-07-28")
    assert Catalog.from_json(redis.data[provider.key]).protocol_version == "2026-07-28"


async def test_fetch_catalog_refuses_a_legacy_session() -> None:
    from fastmcp import Client
    from mcp_server.server import mcp

    with pytest.raises(RuntimeError, match="negotiated 2025-11-25"):
        await catalog_mod.fetch_catalog(Settings(_env_file=None), Client(mcp, mode="legacy"))


async def test_fetch_catalog_pinned_reads_instructions_from_discover(
    live_catalog: Catalog,
) -> None:
    assert live_catalog.protocol_version == "2026-07-28"
    assert live_catalog.instructions  # a pinned client adopts no server instructions itself


async def test_mcp_http_requests_carry_the_current_traceparent_header() -> None:
    """The server's HTTP span parents from the header: without it each POST is a root trace."""
    import httpx2
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    client = catalog_mod.traced_http_client(headers={"X-Customer-Id": "C001"})
    request = httpx2.Request("POST", "http://mcp.test/mcp")
    span = NonRecordingSpan(
        SpanContext(trace_id=0xABC, span_id=0xDEF, is_remote=False, trace_flags=TraceFlags.SAMPLED)
    )
    with trace.use_span(span):
        for hook in client.event_hooks["request"]:
            await hook(request)
    assert request.headers["traceparent"] == f"00-{0xABC:032x}-{0xDEF:016x}-01"

    untraced = httpx2.Request("POST", "http://mcp.test/mcp")
    for hook in client.event_hooks["request"]:
        await hook(untraced)
    assert "traceparent" not in untraced.headers
    await client.aclose()
