"""StateGraph: ingest -> route_skill -> route_tool -> agent <-> tools (plan §4.3).

Routing-only runs compile the same graph with `interrupt_before=["agent"]`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from routing_study.graph import nodes
from routing_study.graph.state import RunContext, TurnState

CHECKPOINT_TTL_MIN = 24 * 60


def build_graph(checkpointer: BaseCheckpointSaver | None = None, *,
                routing_only: bool = False) -> CompiledStateGraph:
    g = StateGraph(TurnState, context_schema=RunContext)
    g.add_node("ingest", nodes.ingest)
    g.add_node("route_skill", nodes.route_skill)
    g.add_node("route_tool", nodes.route_tool)
    g.add_node("agent", nodes.agent)
    g.add_node("tools", nodes.tools)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "route_skill")
    g.add_conditional_edges("route_skill", nodes.after_route,
                            {"next": "route_tool", "end": END})
    g.add_conditional_edges("route_tool", nodes.after_route, {"next": "agent", "end": END})
    g.add_conditional_edges("agent", nodes.after_agent, {"tools": "tools", "end": END})
    g.add_edge("tools", "agent")  # after the tool budget, agent wraps up with no tool call
    return g.compile(checkpointer=checkpointer,
                     interrupt_before=["agent"] if routing_only else None)


@asynccontextmanager
async def redis_checkpointer(redis_url: str) -> AsyncIterator[Any]:
    """AsyncRedisSaver on the app Redis; checkpoints expire after a day."""
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    async with AsyncRedisSaver.from_conn_string(
        redis_url, ttl={"default_ttl": CHECKPOINT_TTL_MIN}
    ) as saver:
        await saver.asetup()
        yield saver
