"""Fakes for graph tests: scripted chat model, in-memory MCP tools, static catalog, fixed router."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from routing_study.catalog import Catalog, Skill, ToolOutcome
from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput


def _tool(name: str, skill: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} description\nWHEN TO USE: {name}",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"order_id": {"type": "string"}},
        },
        "_meta": {
            "br.routingstudy/skill": skill,
            "br.routingstudy/examples": [f"ex {name}"],
            "br.routingstudy/keywords": [name.split("_")[0]],
        },
    }


def make_catalog() -> Catalog:
    tools = [
        _tool("cancel_order", "pedidos_logistica"),
        _tool("escalate_to_human", "global"),
        _tool("get_customer_profile", "global"),
        _tool("get_order_status", "pedidos_logistica"),
        _tool("get_payment_status", "pagamentos_reembolsos"),
        _tool("track_shipment", "pedidos_logistica"),
    ]
    skills = {
        "pedidos_logistica": Skill(
            "pedidos_logistica",
            "Pedidos e entregas",
            ["cadê meu pedido"],
            "---\nname: pedidos_logistica\n---\n# PEDIDOS PLAYBOOK",
        ),
        "pagamentos_reembolsos": Skill(
            "pagamentos_reembolsos",
            "Pagamentos",
            ["boleto"],
            "---\nname: pagamentos_reembolsos\n---\n# PAGAMENTOS",
        ),
    }
    return Catalog(
        url="mem://mcp",
        protocol_version="2026-07-28",
        instructions="SERVER INSTRUCTIONS",
        tools=tools,
        skills=skills,
    )


class StaticCatalog:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    async def get(self) -> tuple[Catalog, str]:
        return self.catalog, "memory"


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        self.calls.append((name, args))
        if name == "get_customer_profile":
            return ToolOutcome(
                "perfil",
                {
                    "status": "completed",
                    "customer_id": "C001",
                    "name": "Ana Souza",
                    "orders": [{"order_id": "O0001", "status": "shipped"}],
                },
                False,
            )
        return ToolOutcome(
            f"{name} ok",
            {"status": "completed", "order_id": "O0001", "total": {"amount": 499.9}},
            False,
        )


class FakeChat:
    """Scripted executor: each call pops the next AIMessage; records every bind and prompt."""

    def __init__(self, script: list[AIMessage | Callable[[], AIMessage]]) -> None:
        self.script = list(script)
        self.binds: list[dict[str, Any]] = []
        self.prompts: list[list[BaseMessage]] = []

    def bind_tools(self, tools: list[dict[str, Any]], **kwargs: Any) -> _Bound:
        self.binds.append({"tools": [t["function"]["name"] for t in tools], **kwargs})
        return _Bound(self)


class _Bound:
    def __init__(self, chat: FakeChat) -> None:
        self.chat = chat

    async def ainvoke(self, messages: list[BaseMessage], config: Any = None) -> AIMessage:
        self.chat.prompts.append(messages)
        nxt = self.chat.script.pop(0)
        return nxt() if callable(nxt) else nxt


def tool_call(name: str, args: dict[str, Any] | None = None, n: int = 1) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args or {}, "id": f"call_{name}_{n}"}])


class FixedRouter:
    """Router returning a fixed choice per level (None = abstain)."""

    name = "regex"

    def __init__(
        self,
        skill: str | None,
        tool: str | None,
        tool_candidates: list[tuple[str, float]] | None = None,
    ) -> None:
        self.skill, self.tool = skill, tool
        self.tool_candidates = tool_candidates or []
        self.inputs: list[RoutingInput] = []

    async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        self.inputs.append(inp)
        choice = self.skill if inp.level == "skill" else self.tool
        cands = self.tool_candidates if inp.level == "tool" else []
        return RouteDecision(
            choice=choice,
            confidence=0.9 if choice else 0.0,
            candidates=cands or ([(choice, 0.9)] if choice else []),
            strategy="regex",
        )
