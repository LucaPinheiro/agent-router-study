"""The checkpointer's Redis client must ride out server stalls and connection bursts.

A local Docker Redis stalls for seconds under VM memory pressure; with redis-py 8 defaults
(5 s read timeout, no retries on `from_url` clients, non-blocking pool) every in-flight case
failed with `TimeoutError: Timeout reading from ...`, and high concurrency hit
`MaxConnectionsError`. A fake RESP server reproduces both without Docker.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as aioredis
from redis.exceptions import TimeoutError

from routing_study.graph.builder import app_redis_client


async def _read_command(reader: asyncio.StreamReader) -> list[bytes]:
    header = await reader.readline()
    if not header:
        raise EOFError
    args = []
    for _ in range(int(header[1:])):
        size = int((await reader.readline())[1:])
        args.append((await reader.readexactly(size + 2))[:-2])
    return args


class FakeRedis:
    """Answers PING/anything with PONG/OK after `delay`; answers nothing until `stall_until`."""

    def __init__(self, stall_s: float = 0.0, delay_s: float = 0.0) -> None:
        self.stall_until = time.monotonic() + stall_s
        self.delay_s = delay_s
        self.url = ""

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                cmd = await _read_command(reader)
                if time.monotonic() < self.stall_until:
                    continue  # stalled server: the request is read, never answered
                await asyncio.sleep(self.delay_s)
                writer.write(b"+PONG\r\n" if cmd[0].upper() == b"PING" else b"+OK\r\n")
                await writer.drain()
        except (EOFError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


async def _serve(fake: FakeRedis) -> AsyncIterator[FakeRedis]:
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    fake.url = f"redis://127.0.0.1:{port}/0"
    async with server:
        yield fake
        server.close()


@pytest.fixture
async def stalled() -> AsyncIterator[FakeRedis]:
    async for fake in _serve(FakeRedis(stall_s=0.3)):
        yield fake


@pytest.fixture
async def slow() -> AsyncIterator[FakeRedis]:
    async for fake in _serve(FakeRedis(delay_s=0.02)):
        yield fake


async def test_default_client_fails_on_a_stall(stalled: FakeRedis) -> None:
    client = aioredis.from_url(stalled.url, socket_timeout=0.2)  # redis-py defaults otherwise
    try:
        with pytest.raises(TimeoutError):
            await client.ping()
    finally:
        await client.aclose()


async def test_app_client_retries_through_a_stall(stalled: FakeRedis) -> None:
    client = app_redis_client(stalled.url, socket_timeout=0.2)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose(close_connection_pool=True)


async def test_app_pool_waits_on_burst(slow: FakeRedis) -> None:
    # redis-py's default pool raises MaxConnectionsError here (seen at --concurrency 32)
    client = app_redis_client(slow.url, max_connections=2)
    try:
        assert all(await asyncio.gather(*(client.ping() for _ in range(10))))
    finally:
        await client.aclose(close_connection_pool=True)


def test_checkpointer_client_settings() -> None:
    client = app_redis_client("redis://localhost:6381/0")
    pool = client.connection_pool
    assert isinstance(pool, aioredis.BlockingConnectionPool)
    assert pool.timeout is None
    assert pool.connection_kwargs["socket_timeout"] >= 30
    assert pool.connection_kwargs["retry"].get_retries() >= 3
    assert TimeoutError in pool.connection_kwargs["retry_on_error"]
