"""The 5 nodes (plan §4.3). One executor serves native (E0) and routed (E1–E9) runs; the only
difference is the exposure policy. Each node opens its own Langfuse span so router spans, the
executor generation and MCP calls nest under it (LangGraph's callback spans do not become the
OTel current span inside a node, so they are not used)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from routing_study.catalog import Catalog, ToolOutcome
from routing_study.graph.state import RunContext, TurnState
from routing_study.llm import call_with_retry
from routing_study.prompts import PROMPT_HASH, system_blocks
from routing_study.routers.base import GLOBAL_OPTION, Message, RoutingInput
from routing_study.routers.pipeline import summary
from routing_study.settings import Settings
from routing_study.tracing.langfuse import span

LOAD_SKILL = "load_skill"
ESCALATION_TEXT = ("Não consegui identificar como resolver seu pedido por aqui. "
                   "Vou encaminhar para um atendente humano.")


def load_skill_tool(catalog: Catalog) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": LOAD_SKILL,
        "description": "Loads a skill: its playbook and tools become available on the next step.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["skill"],
                       "properties": {"skill": {"type": "string", "enum": list(catalog.skills),
                                                "description": "Skill id"}}}}}


def _routing_input(state: TurnState, level: str, loaded_skill: str | None = None) -> RoutingInput:
    turns = state["case"]["turns"]
    return RoutingInput(message=turns[-1]["content"], level=level, loaded_skill=loaded_skill,
                        history=[Message(role=t["role"], content=t["content"])
                                 for t in turns[:-1]])


def _abstain(stage: str) -> dict[str, Any]:
    return {"outcome": "abstained",
            "messages": [AIMessage(ESCALATION_TEXT, name="host",
                                   additional_kwargs={"abstained_at": stage})]}


async def call_mcp(ctx: RunContext, name: str, args: dict[str, Any]) -> ToolOutcome:
    """One `tools/call`; the span is current, so the injected traceparent parents the server."""
    with span(f"mcp.client.call {name}", as_type="tool", input=args) as sp:
        out = await ctx.tools.call(name, args)
        sp.update(output=out.structured or out.text, metadata={"status": out.status},
                  level="ERROR" if out.is_error else "DEFAULT")
        return out


# ---------------------------------------------------------------- nodes


async def ingest(state: TurnState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Gold history -> messages; catalog (cached); customer profile for the context layer."""
    ctx = runtime.context
    with span("ingest") as sp:
        catalog, source = await ctx.catalog.get()
        turns = state["case"]["turns"]
        messages: list[AnyMessage] = [
            HumanMessage(t["content"]) if t["role"] == "user" else AIMessage(t["content"])
            for t in turns]
        profile = await call_mcp(ctx, "get_customer_profile", {})
        sp.update(metadata={"catalog_cache": source, "catalog_hash": catalog.hash,
                            "customer_id": state["case"]["customer_id"],
                            "history_turns": len(turns) - 1})
    return {"messages": messages, "customer": profile.structured, "skill_decision": None,
            "tool_decision": None, "loaded_skill": None, "exposed_tools": [], "outcome": None}


async def route_skill(state: TurnState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    if ctx.skill_pipeline is None:  # native: the executor loads skills itself
        return {}
    catalog, _ = await ctx.catalog.get()
    inp, options = _routing_input(state, "skill"), catalog.skill_options()
    with span("route_skill", input={"message": inp.message,
                                    "options": [o.id for o in options]}) as sp:
        res = await ctx.skill_pipeline.run(inp, options)
        dump = res.model_dump(mode="json")
        sp.update(output={"choice": res.decision.choice}, metadata=summary(dump))
    update: dict[str, Any] = {"skill_decision": dump}
    if res.abstained:
        return update | _abstain("skill")
    choice = res.decision.choice
    return update | {"loaded_skill": None if choice == GLOBAL_OPTION else choice}


async def route_tool(state: TurnState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Tool stage over the chosen skill's tools + globals; exposes top-k + globals."""
    ctx = runtime.context
    if ctx.tool_pipeline is None:
        return {}
    catalog, _ = await ctx.catalog.get()
    skill = state.get("loaded_skill") or GLOBAL_OPTION
    inp, options = _routing_input(state, "tool", loaded_skill=skill), catalog.tool_options(skill)
    k = ctx.tool_pipeline.stage.expose_top_k
    with span("route_tool", input={"message": inp.message,
                                   "options": [o.id for o in options]}) as sp:
        res = await ctx.tool_pipeline.run(inp, options)
        dump = res.model_dump(mode="json")
        exposed: list[str] = []
        if not res.abstained:
            valid = {o.id for o in options}
            # LLM-style routers rank only their choice: fill top-k from the consulted steps
            ranked = [res.decision.choice, *(c for c, _ in res.decision.candidates),
                      *(c for step in res.steps for c, _ in step.candidates)]
            top = [c for c in dict.fromkeys(ranked) if c in valid][:k]
            exposed = catalog.ordered({*top, *catalog.global_tools})
        sp.update(output={"choice": res.decision.choice},
                  metadata={**(summary(dump) or {}), "top_k": k, "exposed_tools": exposed})
    update: dict[str, Any] = {"tool_decision": dump}
    if res.abstained:
        return update | _abstain("tool")
    return update | {"exposed_tools": exposed}


def _turn_messages(state: TurnState) -> list[AnyMessage]:
    """Messages produced in this turn (after the gold history)."""
    return state["messages"][len(state["case"]["turns"]):]


def _native_exposure(catalog: Catalog, loaded_skill: str | None) -> list[str]:
    names = set(catalog.global_tools)
    if loaded_skill:
        names |= set(catalog.tools_for(loaded_skill))
    return catalog.ordered(names)


async def agent(state: TurnState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    if ctx.chat is None:
        raise RuntimeError("agent node reached without an executor chat model")
    catalog, _ = await ctx.catalog.get()
    skill = state.get("loaded_skill")
    exposed = (_native_exposure(catalog, skill) if ctx.native else list(state["exposed_tools"]))
    schemas = [catalog.openai_tool(n) for n in exposed]
    if ctx.native:
        schemas.append(load_skill_tool(catalog))
    tool_choice: Any = None
    wrap_up = state.get("outcome") == "loop_limit"
    if wrap_up:  # last step after the tool budget: same tools (history has tool calls), none
        tool_choice = "none"
    elif not ctx.native and ctx.tool_pipeline and ctx.tool_pipeline.stage.expose_top_k == 1:
        first_call = not any(isinstance(m, ToolMessage) for m in _turn_messages(state))
        if first_call:  # forced only on the first step; the answer step must be free
            tool_choice = state["tool_decision"]["decision"]["choice"]
    bound = ctx.chat.bind_tools(schemas, tool_choice=tool_choice, parallel_tool_calls=False)
    system = SystemMessage(content=system_blocks(catalog, native=ctx.native, skill=skill,
                                                 customer=state.get("customer")))
    messages = [system, *state["messages"]]
    model = ctx.settings.executor.model if ctx.settings.executor else "executor"
    with span("agent", metadata={"exposed_tools": exposed, "prompt_hash": PROMPT_HASH,
                                 "prompts": ctx.prompt_versions,
                                 "loaded_skill": skill, "tool_choice": tool_choice}) as sp:
        ai: AIMessage = await call_with_retry(
            lambda: bound.ainvoke(messages, config={"callbacks": ctx.callbacks}),
            model=model, settings=ctx.settings)
        sp.update(output={"tool_calls": ai.tool_calls, "content": ai.text})
    update: dict[str, Any] = {"messages": [ai], "exposed_tools": exposed}
    if not ai.tool_calls and not wrap_up:
        update["outcome"] = "answered"
    return update


async def tools(state: TurnState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Executes the last AIMessage's tool calls: MCP tools, or the host-side `load_skill`."""
    ctx = runtime.context
    catalog, _ = await ctx.catalog.get()
    ai = state["messages"][-1]
    assert isinstance(ai, AIMessage)
    exposed = set(state.get("exposed_tools") or [])
    update: dict[str, Any] = {}
    out: list[ToolMessage] = []
    with span("tools"):
        for tc in ai.tool_calls:
            name, args, tid = tc["name"], tc.get("args") or {}, tc["id"]
            if name == LOAD_SKILL and ctx.native:
                skill = args.get("skill")
                with span("load_skill", as_type="tool", input=args):
                    if skill in catalog.skills:
                        update["loaded_skill"] = skill
                        text = f"Skill {skill} loaded. Its tools are now available."
                    else:
                        text = f"Unknown skill {skill!r}. Options: {list(catalog.skills)}."
                out.append(ToolMessage(text, tool_call_id=tid, name=name,
                                       status="success" if skill in catalog.skills else "error"))
            elif name not in exposed:
                out.append(ToolMessage(f"Tool {name!r} is not available.", tool_call_id=tid,
                                       name=name, status="error",
                                       artifact={"is_error": True, "structured": None}))
            else:
                res = await call_mcp(ctx, name, args)
                out.append(ToolMessage(res.text, tool_call_id=tid, name=name,
                                       status="error" if res.is_error else "success",
                                       artifact={"is_error": res.is_error,
                                                 "structured": res.structured}))
    update["messages"] = out
    rounds = sum(1 for m in _turn_messages(state) if isinstance(m, AIMessage) and m.tool_calls)
    if rounds >= max_tool_rounds(ctx.settings):
        update["outcome"] = "loop_limit"  # one last agent step, with tool_choice="none"
    return update


def max_tool_rounds(settings: Settings) -> int:
    """Every tool round counts, load_skill included; +1 leaves room for loading a skill."""
    return (settings.executor.max_tool_iterations if settings.executor else 3) + 1


# ---------------------------------------------------------------- edges


def after_route(state: TurnState) -> str:
    return "end" if state.get("outcome") == "abstained" else "next"


def after_agent(state: TurnState) -> str:
    last = state["messages"][-1]
    if state.get("outcome") == "loop_limit":
        return "end"
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "end"
