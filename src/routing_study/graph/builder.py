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
# The app Redis runs in Docker Desktop and stalls for seconds under VM memory pressure (swapped
# pages, slow BGSAVE). redis-py 8 defaults (5 s read timeout, 0 retries on from_url clients,
# non-blocking pool capped at 100) turned each stall into failed cases, ~one per in-flight case.
REDIS_SOCKET_TIMEOUT_S = 30.0
REDIS_RETRIES = 3  # checkpoint writes are keyed puts (JSON.SET/ZADD/EXPIRE): safe to resend
REDIS_MAX_CONNECTIONS = 100


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None, *, routing_only: bool = False
) -> CompiledStateGraph:
    g = StateGraph(TurnState, context_schema=RunContext)
    g.add_node("ingest", nodes.ingest)
    g.add_node("route_skill", nodes.route_skill)
    g.add_node("route_tool", nodes.route_tool)
    g.add_node("agent", nodes.agent)
    g.add_node("tools", nodes.tools)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "route_skill")
    g.add_conditional_edges("route_skill", nodes.after_route, {"next": "route_tool", "end": END})
    g.add_conditional_edges("route_tool", nodes.after_route, {"next": "agent", "end": END})
    g.add_conditional_edges("agent", nodes.after_agent, {"tools": "tools", "end": END})
    g.add_edge("tools", "agent")  # after the tool budget, agent wraps up with no tool call
    return g.compile(
        checkpointer=checkpointer, interrupt_before=["agent"] if routing_only else None
    )


def app_redis_client(
    redis_url: str,
    *,
    socket_timeout: float = REDIS_SOCKET_TIMEOUT_S,
    retries: int = REDIS_RETRIES,
    max_connections: int = REDIS_MAX_CONNECTIONS,
) -> Any:
    """Async client that rides out Redis stalls: long read timeout, retries on timeout and
    connection errors, and a blocking pool (waits for a free connection instead of raising
    MaxConnectionsError at high concurrency)."""
    from redis.asyncio import BlockingConnectionPool, Redis
    from redis.asyncio.retry import Retry
    from redis.backoff import ExponentialWithJitterBackoff
    from redis.exceptions import ConnectionError, TimeoutError

    pool = BlockingConnectionPool.from_url(
        redis_url,
        max_connections=max_connections,
        timeout=None,
        socket_timeout=socket_timeout,
        retry=Retry(ExponentialWithJitterBackoff(base=0.05, cap=1.0), retries),
        retry_on_error=[ConnectionError, TimeoutError],
        protocol=2,  # what redisvl uses for its own clients
    )
    return Redis(connection_pool=pool)


@asynccontextmanager
async def redis_checkpointer(redis_url: str) -> AsyncIterator[Any]:
    """AsyncRedisSaver on the app Redis; checkpoints expire after a day."""
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    client = app_redis_client(redis_url)
    try:
        async with AsyncRedisSaver.from_conn_string(
            redis_client=client, ttl={"default_ttl": CHECKPOINT_TTL_MIN}
        ) as saver:
            await saver.asetup()
            yield saver
    finally:
        await client.aclose(close_connection_pool=True)
