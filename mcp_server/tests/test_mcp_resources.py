import json
from pathlib import Path

import pytest
import yaml
from fastmcp import Client
from mcp_fixtures import meta
from mcp_server.export import tools_list_payload
from mcp_server.server import SKILL_IDS, SKILL_IDS_LARGE
from mcp_server.telemetry import parent_context
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.testclient import TestClient

SKILLS_BY_PROFILE = {"small": SKILL_IDS, "large": SKILL_IDS_LARGE}
EXPORTS = {"small": "tools_list.json", "large": "tools_list_large.json"}
RDNS = "br.routingstudy"


async def test_resources_listed_and_readable(client: Client, profile: str) -> None:
    skills = SKILLS_BY_PROFILE[profile]
    uris = {str(r.uri) for r in await client.list_resources()}
    assert uris == {f"skill://{s}/SKILL.md" for s in skills} | {"shop://policies"}
    tools = {t.name: t for t in await client.list_tools()}
    for skill in skills:
        [content] = await client.read_resource(f"skill://{skill}/SKILL.md")
        assert content.mime_type == "text/markdown"
        _, front, body = content.text.split("---", 2)
        fm = yaml.safe_load(front)
        assert fm["name"] == skill and fm["description"]
        assert 3 <= len(fm["examples"]) <= 5
        assert len(fm["allowed-tools"]) == (5 if skill in SKILL_IDS else 6)
        assert set(fm["allowed-tools"]) == {
            n for n, t in tools.items() if t.meta[f"{RDNS}/skill"] == skill
        }
        for name in fm["allowed-tools"]:
            assert tools[name].meta[f"{RDNS}/skill"] == skill
        assert body.strip()


async def test_policies_resource(client: Client) -> None:
    [content] = await client.read_resource("shop://policies")
    assert content.mime_type == "application/json"
    policies = json.loads(content.text)
    assert policies["out_of_scope"] and len(policies["articles"]) >= 5


async def test_instructions_and_no_skills_extension(client: Client) -> None:
    assert client.protocol_version == "2026-07-28"
    instructions = client.instructions
    assert instructions and "Fora do escopo" in instructions
    assert len(instructions) // 4 <= 500
    caps = client.server_capabilities.model_dump(by_alias=True, exclude_none=True)
    assert "io.modelcontextprotocol/skills" not in json.dumps(caps)


async def test_tools_list_json_is_current(client: Client, profile: str) -> None:
    exported = json.loads((Path(__file__).parents[1] / EXPORTS[profile]).read_text())
    assert exported == await tools_list_payload(client)


async def test_span_joins_caller_trace(client: Client) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)  # global; no exporter is configured in tests otherwise
    with provider.get_tracer("host").start_as_current_span("turn") as turn:
        await client.call_tool("get_order_status", {"order_id": "O0001"}, meta=meta("C001"))
        await client.call_tool(
            "cancel_order", {"order_id": "O9999"}, meta=meta("C001"), raise_on_error=False
        )
    spans = {s.name: s for s in exporter.get_finished_spans()}
    ok = spans["mcp.tools/call get_order_status"]
    assert ok.context.trace_id == turn.get_span_context().trace_id
    assert ok.attributes["tool"] == "get_order_status"
    assert ok.attributes["status"] == "completed" and ok.attributes["latency_ms"] >= 0
    err = spans["mcp.tools/call cancel_order"]
    assert err.attributes["status"] == "error" and err.attributes["code"] == "NOT_FOUND"


def test_parent_context_from_meta_or_header() -> None:
    header_tp = f"00-{'a' * 32}-{'b' * 16}-01"
    meta_tp = f"00-{'c' * 32}-{'d' * 16}-01"

    def trace_id(ctx: object) -> str:
        return format(trace.get_current_span(ctx).get_span_context().trace_id, "032x")

    assert parent_context({}, None) is None
    assert trace_id(parent_context({"traceparent": header_tp}, None)) == "a" * 32
    assert trace_id(parent_context({"traceparent": header_tp}, {"traceparent": meta_tp})) == (
        "c" * 32
    )


def test_http_app_health_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_server import app as app_mod

    monkeypatch.setattr(app_mod, "MCP_TOKEN", "t" * 32)
    with TestClient(app_mod.app) as http:
        assert http.get("/healthz").status_code == 200
        assert http.get("/readyz").json()["tools"] == 18
        denied = http.post("/mcp", json={})
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"].startswith("Bearer")
        wrong = http.post("/mcp", json={}, headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401


def test_security_mcp_token_has_no_default_and_needs_16_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp_server import app as app_mod

    for weak in ("", "dev-token", "x" * 15):
        monkeypatch.setattr(app_mod, "MCP_TOKEN", weak)
        with pytest.raises(RuntimeError, match="MCP_TOKEN"), TestClient(app_mod.app):
            pass
    good = "s3cr3t-token-0123456789"
    monkeypatch.setattr(app_mod, "MCP_TOKEN", good)
    with TestClient(app_mod.app) as http:
        ok = http.post("/mcp", json={}, headers={"Authorization": f"Bearer {good}"})
        assert ok.status_code != 401
