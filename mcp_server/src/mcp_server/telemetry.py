"""OpenTelemetry: optional OTLP/HTTP exporter + W3C traceparent extraction (header and _meta)."""

from __future__ import annotations

import base64
import logging
import os
from collections.abc import Mapping
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import propagate, trace

logger = logging.getLogger(__name__)
TRACER_NAME = "mcp_server"
_configured = False


def setup_tracing() -> bool:
    """Install an OTLP/HTTP exporter when OTEL_EXPORTER_OTLP_ENDPOINT is set; no-op otherwise.

    Langfuse: OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel and
    LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY (basic auth) unless OTEL_EXPORTER_OTLP_HEADERS is set.

    Only spans inside a caller's trace are recorded (`ParentBased(ALWAYS_OFF)`): a request
    without a W3C `traceparent` (health probes, untraced clients) would otherwise open a root
    trace per HTTP request in Langfuse.
    """
    global _configured
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if _configured or not endpoint:
        return _configured
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ParentBased

    headers: dict[str, str] | None = None
    pk, sk = os.getenv("LANGFUSE_PUBLIC_KEY"), os.getenv("LANGFUSE_SECRET_KEY")
    if pk and sk and not os.getenv("OTEL_EXPORTER_OTLP_HEADERS"):
        token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        headers = {"Authorization": f"Basic {token}"}
    exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces", headers=headers)
    service = os.getenv("OTEL_SERVICE_NAME", "mcp-server")
    provider = TracerProvider(
        resource=Resource.create({"service.name": service}), sampler=ParentBased(ALWAYS_OFF)
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True
    logger.info("OTLP trace exporter enabled: %s", endpoint)
    return True


def parent_context(
    headers: Mapping[str, str], meta: Mapping[str, Any] | None
) -> otel_context.Context | None:
    """Parent for the tool span. `_meta.traceparent` wins over the HTTP header.

    Returns None (use the current context) when the active span already belongs to the
    incoming trace (FastMCP's own server span extracted from `_meta`) or nothing was sent.
    """
    carrier: dict[str, str] = {}
    for key in ("traceparent", "tracestate"):
        value = (meta or {}).get(key) or headers.get(key)
        if value:
            carrier[key] = str(value)
    if "traceparent" not in carrier:
        return None
    extracted = propagate.extract(carrier)
    incoming = trace.get_current_span(extracted).get_span_context()
    current = trace.get_current_span().get_span_context()
    if current.is_valid and current.trace_id == incoming.trace_id:
        return None
    return extracted
