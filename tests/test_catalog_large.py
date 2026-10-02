"""Host view of the two catalog profiles (in process, no network): the large profile passes the
host's SKILL.md `allowed-tools` vs `_meta` consistency check and yields 10 skills + globals;
the small profile served by the profile-aware server keeps the frozen phase-1 catalog hash."""

from __future__ import annotations

from fastmcp import Client

from routing_study.catalog import fetch_catalog
from routing_study.routers.base import GLOBAL_OPTION
from routing_study.settings import load_settings

SMALL_HASH = "128584617807"


async def _catalog(profile: str):  # type: ignore[no-untyped-def]
    from mcp_server.server import build_server

    settings = load_settings("config/experiments/e0_native.yaml")
    return await fetch_catalog(settings, client=Client(build_server(profile)))


async def test_small_profile_keeps_the_phase1_catalog_hash() -> None:
    assert (await _catalog("small")).hash == SMALL_HASH


async def test_large_profile_host_catalog() -> None:
    catalog = await _catalog("large")  # raises if any allowed-tools != _meta skill
    assert catalog.hash != SMALL_HASH
    assert len(catalog.tools) == 62 and len(catalog.skills) == 10
    assert len(catalog.global_tools) == 5
    options = catalog.skill_options()
    assert [o.id for o in options][-1] == GLOBAL_OPTION and len(options) == 11
    for skill_id in catalog.skills:
        tool_opts = catalog.tool_options(skill_id)
        assert len(tool_opts) == len(catalog.tools_for(skill_id)) + 5
        assert all(o.examples and o.keywords for o in tool_opts)
    # the overlay makes the confusable pointers two-sided at skill level too
    avoid = {o.id: o.avoid for o in options}
    assert any("assinaturas" in skills for _, skills in avoid["pedidos_logistica"])
    assert any("pedidos_logistica" in skills for _, skills in avoid["assinaturas"])
