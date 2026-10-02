import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastmcp import Client
from mcp_fixtures import SERVERS
from mcp_server.server import PROFILES
from opentelemetry import trace
from opentelemetry.util._once import Once


@pytest.fixture(autouse=True)
def _hermetic_otel(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No ambient OTEL_* exporter, and a fresh global TracerProvider per test (review B14):
    `trace.set_tracer_provider` is set-once per process, so one test's provider (or the app's
    OTLP exporter) would otherwise leak into every later test."""
    from mcp_server import telemetry

    for key in [k for k in os.environ if k.startswith("OTEL_")]:
        monkeypatch.delenv(key)

    def reset() -> None:
        trace._TRACER_PROVIDER_SET_ONCE = Once()
        trace._TRACER_PROVIDER = None
        telemetry._configured = False

    reset()
    yield
    reset()


@pytest.fixture(params=PROFILES)
def profile(request: pytest.FixtureRequest) -> str:
    """Catalog profile: every test that takes `client` runs against both servers."""
    return request.param


@pytest.fixture
async def client(profile: str) -> AsyncIterator[Client]:
    async with Client(SERVERS[profile]) as c:
        yield c
