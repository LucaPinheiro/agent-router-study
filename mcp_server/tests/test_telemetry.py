"""Server tracing: only spans inside a caller's trace are recorded; probes are not traced."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.sampling import Decision
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags


def test_untraced_paths_are_the_probes() -> None:
    from mcp_server.app import untraced

    assert untraced({"type": "http", "path": "/healthz"})
    assert untraced({"type": "http", "path": "/readyz"})
    assert not untraced({"type": "http", "path": "/mcp"})


def test_root_spans_are_dropped_and_children_of_a_caller_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp_server import telemetry

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9/api/public/otel")
    assert telemetry.setup_tracing()
    sampler = trace.get_tracer_provider().sampler  # type: ignore[attr-defined]

    root = sampler.should_sample(None, 0x1, "POST /{path}")
    assert root.decision == Decision.DROP

    caller = SpanContext(
        trace_id=0xABC, span_id=0xDEF, is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED)
    )
    parent = trace.set_span_in_context(NonRecordingSpan(caller))
    child = sampler.should_sample(parent, 0xABC, "POST /{path}")
    assert child.decision == Decision.RECORD_AND_SAMPLE
