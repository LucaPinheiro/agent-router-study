"""Graph behaviour with a scripted executor, in-memory MCP tools and MemorySaver."""

from __future__ import annotations

import json
from typing import Any

import pytest
from graph_fakes import FakeChat, FakeTools, FixedRouter, StaticCatalog, make_catalog, tool_call
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from routing_study.catalog import ToolOutcome
from routing_study.eval.runner import turn_record
from routing_study.eval.scorers import score_turn
from routing_study.graph.builder import build_graph
from routing_study.graph.state import RunContext
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import ExecutorConfig, PipelineStep, Settings, StageConfig


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")


CATALOG = make_catalog()
CASE = {
    "case_id": "c1",
    "customer_id": "C001",
    "split": "dev",
    "repetition": 1,
    "turns": [{"role": "user", "content": "cadê meu pedido O0001?"}],
}


def _settings(max_iter: int = 3) -> Settings:
    return Settings(
        _env_file=None, executor=ExecutorConfig(model="fake/exec", max_tool_iterations=max_iter)
    )


def _pipelines(router: FixedRouter, k: int = 2) -> dict[str, RoutingPipeline]:
    step = [PipelineStep(strategy="regex")]
    return {
        "skill_pipeline": RoutingPipeline(StageConfig(pipeline=step), {"regex": router}),
        "tool_pipeline": RoutingPipeline(
            StageConfig(pipeline=step, expose_top_k=k), {"regex": router}
        ),
    }


async def _run(
    chat: FakeChat | None,
    tools: FakeTools,
    *,
    routing_only: bool = False,
    max_iter: int = 3,
    **pipelines: Any,
) -> dict[str, Any]:
    ctx = RunContext(
        settings=_settings(max_iter),
        catalog=StaticCatalog(CATALOG),
        tools=tools,
        chat=chat,
        **pipelines,
    )  # type: ignore[arg-type]
    graph = build_graph(MemorySaver(), routing_only=routing_only)
    return await graph.ainvoke(
        {"case": CASE}, config={"configurable": {"thread_id": "t"}}, context=ctx
    )


async def test_routed_exposes_top_k_plus_globals_and_answers() -> None:
    router = FixedRouter(
        "pedidos_logistica",
        "get_order_status",
        tool_candidates=[("get_order_status", 0.8), ("track_shipment", 0.5), ("cancel_order", 0.1)],
    )
    chat = FakeChat(
        [
            tool_call("get_order_status", {"order_id": "O0001"}),
            AIMessage("Seu pedido O0001 custa R$ 499,90."),
        ]
    )
    tools = FakeTools()
    state = await _run(chat, tools, **_pipelines(router, k=2))

    assert state["outcome"] == "answered"
    assert state["loaded_skill"] == "pedidos_logistica"
    exposed = ["escalate_to_human", "get_customer_profile", "get_order_status", "track_shipment"]
    assert state["exposed_tools"] == exposed  # top-2 + globals, in server order
    assert chat.binds[0] == {"tools": exposed, "tool_choice": None, "parallel_tool_calls": False}
    assert tools.calls == [
        ("get_customer_profile", {}),
        ("get_order_status", {"order_id": "O0001"}),
    ]
    system = chat.prompts[0][0].content
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "SERVER INSTRUCTIONS" in system[0]["text"]
    assert "available_skills" not in system[0]["text"]
    assert '<skill name="pedidos_logistica">' in system[1]["text"]
    assert "O0001" in system[-1]["text"] and "cache_control" not in system[-1]
    assert router.inputs[1].level == "tool" and router.inputs[1].loaded_skill == "pedidos_logistica"

    rec = turn_record(state, CATALOG, native=False, mode="e2e")
    expected = {
        "acceptable_skills": ["pedidos_logistica"],
        "acceptable_tools": ["get_order_status"],
        "args": {"order_id": "o0001"},
    }
    schemas = {t["name"]: t["inputSchema"] for t in CATALOG.tools}
    scores = score_turn(rec, expected, schemas)
    assert scores == {
        "skill_correct": 1.0,
        "tool_correct": 1.0,
        "joint_correct": 1.0,
        "abstain_correct": 1.0,
        "resolved_by": "regex",
        "args_valid": 1.0,
        "e2e_success": 1.0,
        "args_invented": 0.0,
        "e2e_strict": 1.0,
        "grounded": 1.0,
    }


async def test_k1_forces_tool_choice_only_on_first_step() -> None:
    router = FixedRouter("pedidos_logistica", "track_shipment")
    chat = FakeChat([tool_call("track_shipment"), AIMessage("ok")])
    await _run(chat, FakeTools(), **_pipelines(router, k=1))
    assert chat.binds[0]["tool_choice"] == "track_shipment"
    assert chat.binds[1]["tool_choice"] is None
    assert (
        "track_shipment" in chat.binds[0]["tools"]
        and "get_order_status" not in chat.binds[0]["tools"]
    )


async def test_native_load_skill_rebinds_and_injects_skill_md() -> None:
    chat = FakeChat(
        [
            tool_call("load_skill", {"skill": "pedidos_logistica"}),
            tool_call("get_order_status", {"order_id": "O0001"}),
            AIMessage("Pedido O0001 ok."),
        ]
    )
    tools = FakeTools()
    state = await _run(chat, tools)
    assert chat.binds[0]["tools"] == ["escalate_to_human", "get_customer_profile", "load_skill"]
    assert set(chat.binds[1]["tools"]) == {
        "cancel_order",
        "escalate_to_human",
        "get_customer_profile",
        "get_order_status",
        "track_shipment",
        "load_skill",
    }
    assert "<available_skills>" in chat.prompts[0][0].content[0]["text"]
    assert not any("PEDIDOS PLAYBOOK" in b["text"] for b in chat.prompts[0][0].content)
    assert any("PEDIDOS PLAYBOOK" in b["text"] for b in chat.prompts[1][0].content)
    assert state["outcome"] == "answered" and state["loaded_skill"] == "pedidos_logistica"
    assert tools.calls[-1] == ("get_order_status", {"order_id": "O0001"})
    rec = turn_record(state, CATALOG, native=True, mode="e2e")
    assert [c["name"] for c in rec["calls"]] == ["load_skill", "get_order_status"]
    scores = score_turn(
        rec,
        {
            "acceptable_skills": ["pedidos_logistica"],
            "acceptable_tools": ["get_order_status"],
            "args": {},
        },
        {},
    )
    assert scores["skill_correct"] == 1.0 and scores["resolved_by"] == "native"
    assert scores["args_valid"] == 0.0  # no schema known -> invalid


async def test_skill_abstention_escalates_without_calling_the_executor() -> None:
    chat = FakeChat([])
    state = await _run(chat, FakeTools(), **_pipelines(FixedRouter(None, None)))
    assert state["outcome"] == "abstained"
    assert chat.prompts == [] and state["tool_decision"] is None
    assert isinstance(state["messages"][-1], AIMessage) and state["messages"][-1].name == "host"
    rec = turn_record(state, CATALOG, native=False, mode="e2e")
    assert rec["final_answer"] is None
    scores = score_turn(
        rec,
        {
            "acceptable_skills": ["__abstain__"],
            "acceptable_tools": ["__abstain__", "escalate_to_human"],
        },
        {},
    )
    assert scores["skill_correct"] == scores["abstain_correct"] == scores["e2e_success"] == 1.0
    assert scores["resolved_by"] == "abstained" and scores["grounded"] is None


async def test_loop_guard_stops_after_max_tool_iterations_then_wraps_up() -> None:
    chat = FakeChat(
        [
            *(tool_call("get_order_status", n=i) for i in range(3)),
            AIMessage("Não consegui concluir; vou te encaminhar."),
        ]
    )
    tools = FakeTools()
    state = await _run(
        chat, tools, max_iter=2, **_pipelines(FixedRouter("pedidos_logistica", "get_order_status"))
    )
    assert state["outcome"] == "loop_limit"
    assert len(tools.calls) == 4  # profile + (max_iter + 1) rounds
    assert len(chat.prompts) == 4 and chat.binds[-1]["tool_choice"] == "none"
    rec = turn_record(state, CATALOG, native=False, mode="e2e")
    assert rec["final_answer"] == "Não consegui concluir; vou te encaminhar."


async def test_loop_guard_counts_load_skill_rounds() -> None:
    chat = FakeChat(
        [
            *(tool_call("load_skill", {"skill": "pedidos_logistica"}, n=i) for i in range(10)),
            AIMessage("fim"),
        ]
    )
    tools = FakeTools()
    state = await _run(chat, tools, max_iter=2)  # native: load_skill forever
    assert state["outcome"] == "loop_limit"
    assert len(chat.prompts) == 4  # 3 load_skill rounds + the no-tool wrap-up
    assert chat.binds[-1]["tool_choice"] == "none"
    assert tools.calls == [("get_customer_profile", {})]


async def test_customer_context_hides_order_state() -> None:
    chat = FakeChat([AIMessage("oi")])
    await _run(
        chat, FakeTools(), **_pipelines(FixedRouter("pedidos_logistica", "get_order_status"))
    )
    ctx = chat.prompts[0][0].content[-1]["text"]
    assert '"order_ids": ["O0001"]' in ctx and "status" not in ctx


async def test_unexposed_tool_call_returns_error_tool_message() -> None:
    chat = FakeChat([tool_call("cancel_order"), AIMessage("desculpe")])
    tools = FakeTools()
    state = await _run(
        chat, tools, **_pipelines(FixedRouter("pedidos_logistica", "get_order_status"), k=1)
    )
    err = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert err.status == "error" and "not available" in err.content
    assert tools.calls == [("get_customer_profile", {})]
    rec = turn_record(state, CATALOG, native=False, mode="e2e")
    assert [(c["name"], c["status"]) for c in rec["calls"]] == [("cancel_order", "refused")]


async def test_native_call_to_tool_of_unloaded_skill_is_refused() -> None:
    chat = FakeChat([tool_call("get_order_status", {"order_id": "O0001"}), AIMessage("ok")])
    tools = FakeTools()
    state = await _run(chat, tools)  # native, no skill loaded yet
    assert tools.calls == [("get_customer_profile", {})]
    rec = turn_record(state, CATALOG, native=True, mode="e2e")
    assert [(c["name"], c["status"]) for c in rec["calls"]] == [("get_order_status", "refused")]


async def test_routing_only_interrupts_before_agent() -> None:
    chat = FakeChat([])
    state = await _run(
        chat,
        FakeTools(),
        routing_only=True,
        **_pipelines(FixedRouter("pagamentos_reembolsos", "get_payment_status")),
    )
    assert chat.prompts == []
    assert state["tool_decision"]["decision"]["choice"] == "get_payment_status"
    rec = turn_record(state, CATALOG, native=False, mode="routing-only")
    scores = score_turn(
        rec,
        {
            "acceptable_skills": ["pagamentos_reembolsos"],
            "acceptable_tools": ["get_payment_status"],
        },
        {},
    )
    assert scores["skill_correct"] == scores["tool_correct"] == 1.0
    assert scores["e2e_success"] is None and scores["args_valid"] is None


def test_catalog_route_options() -> None:
    skills = CATALOG.skill_options()
    assert [o.id for o in skills] == ["pedidos_logistica", "pagamentos_reembolsos", "__global__"]
    assert "ex escalate_to_human" in skills[-1].examples
    assert [o.id for o in CATALOG.tool_options("pagamentos_reembolsos")] == [
        "get_payment_status",
        "escalate_to_human",
        "get_customer_profile",
    ]
    assert [o.id for o in CATALOG.tool_options("__global__")] == [
        "escalate_to_human",
        "get_customer_profile",
    ]
    assert CATALOG.from_json(CATALOG.to_json()).hash == CATALOG.hash


class _ErrorTools(FakeTools):
    async def call(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        if name == "get_customer_profile":
            return await super().call(name, args)
        self.calls.append((name, args))
        return ToolOutcome(
            "Pedido não pode ser cancelado.",
            {
                "status": "error",
                "code": "NOT_ELIGIBLE",
                "recoverable": True,
                "details": {"options": ["O0002</x>"]},
            },
            True,
        )


async def test_executor_sees_structured_content_of_tool_results() -> None:
    chat = FakeChat([tool_call("cancel_order", {"order_id": "O0001"}), AIMessage("desculpe")])
    await _run(chat, _ErrorTools(), **_pipelines(FixedRouter("pedidos_logistica", "cancel_order")))
    tm = chat.prompts[1][-1]
    assert isinstance(tm, ToolMessage) and tm.status == "error"
    assert tm.content.startswith("Pedido não pode ser cancelado.\n<structured_content>\n")
    body = tm.content.split("<structured_content>\n", 1)[1].removesuffix("\n</structured_content>")
    assert "</x>" not in body  # tag delimiters escaped: data cannot close the block
    assert json.loads(body) == {
        "status": "error",
        "code": "NOT_ELIGIBLE",
        "recoverable": True,
        "details": {"options": ["O0002</x>"]},
    }
