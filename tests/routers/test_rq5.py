"""RQ5 leave-tools-out harness (docs/rq5-design.md): catalog filter, regex overlays, manifest
overrides, config hash and the table's statistics."""

from __future__ import annotations

from pathlib import Path

import pytest

from routing_study.catalog import Catalog, CatalogProvider, fetch_catalog
from routing_study.eval.manifest import ManifestRun, load_run_settings
from routing_study.eval.rq5 import (
    RunKey,
    catalog_effort,
    condition_stats,
    held_out_tools,
    parse_run,
    rules_effort,
)
from routing_study.eval.runner import config_hash
from routing_study.routers.regex import RegexRules
from routing_study.settings import CatalogConfig, Settings, load_settings

HELD = ["get_refund_status", "reschedule_delivery", "generate_return_label"]
BASE = "config/rq5/regex_rules_base.yaml"
ORIGINAL = "config/rq5/regex_overlay_original.yaml"
ENGINEERED = "config/rq5/regex_overlay_engineered.yaml"


def _expanded(rules: RegexRules) -> dict[str, list[tuple[str, float]]]:
    return {k: sorted((r.pattern, r.weight) for r in v) for k, v in rules.rules.items()}


# ---------------------------------------------------------------- regex overlays


def test_held_out_tools_record() -> None:
    assert held_out_tools() == HELD


def test_base_plus_original_overlay_is_production() -> None:
    prod = RegexRules.load("config/regex_rules.yaml")
    split = RegexRules.load(BASE, [ORIGINAL])
    assert _expanded(split) == _expanded(prod)
    assert split.full_score == prod.full_score


def test_base_has_no_rules_for_held_out_tools() -> None:
    base = RegexRules.load(BASE)
    assert not set(HELD) & set(base.rules)
    assert not {"RESCHEDULE", "LABEL"} & set(base.defs)


def test_engineered_overlay_loads_and_covers_the_tools() -> None:
    eng = RegexRules.load(BASE, [ENGINEERED])
    assert set(HELD) <= set(eng.rules)


def test_overlay_rejects_redefined_defs_and_other_keys(tmp_path: Path) -> None:
    dup = tmp_path / "dup.yaml"
    dup.write_text("defs:\n  ORDER: 'x'\n")
    with pytest.raises(ValueError, match="already defined"):
        RegexRules.load(BASE, [dup])
    extra = tmp_path / "extra.yaml"
    extra.write_text("full_score: 2.0\n")
    with pytest.raises(ValueError, match="only defs/rules"):
        RegexRules.load(BASE, [extra])


def test_overlay_rules_append_and_may_use_base_defs(tmp_path: Path) -> None:
    ov = tmp_path / "ov.yaml"
    ov.write_text(
        "defs:\n  NEW: 'abc'\nrules:\n  cancel_order:\n    - { pattern: '{{NEW}}{{ID}}' }\n"
    )
    base = RegexRules.load(BASE)
    merged = RegexRules.load(BASE, [ov])
    assert len(merged.rules["cancel_order"]) == len(base.rules["cancel_order"]) + 1
    assert merged.rules["cancel_order"][-1].pattern.startswith("(?:abc)(?:")


# ---------------------------------------------------------------- catalog filter


@pytest.fixture(scope="module")
async def full_catalog() -> Catalog:
    from fastmcp import Client
    from mcp_server.server import mcp

    return await fetch_catalog(Settings(_env_file=None), Client(mcp))


async def test_fetch_catalog_applies_exclusion() -> None:
    from fastmcp import Client
    from mcp_server.server import mcp

    s = Settings(_env_file=None, catalog=CatalogConfig(exclude_tools=HELD))
    cat = await fetch_catalog(s, Client(mcp))
    assert not any(cat.has_tool(t) for t in HELD)
    assert len(cat.tools) == 18 - 3


def test_without_drops_tools_options_examples_and_avoid_targets(full_catalog: Catalog) -> None:
    red = full_catalog.without(HELD)
    assert red.hash != full_catalog.hash
    assert full_catalog.has_tool("get_refund_status")  # the original is untouched
    ids = {o.id for o in red.tool_options("pagamentos_reembolsos")}
    assert "get_refund_status" not in ids and "request_refund" in ids
    copied = set(full_catalog.meta("get_refund_status", "examples"))
    assert copied & set(full_catalog.skills["pagamentos_reembolsos"].examples)
    assert not copied & set(red.skills["pagamentos_reembolsos"].examples)
    for opt in red.tool_options("pagamentos_reembolsos"):
        assert all("get_refund_status" not in targets for _, targets in opt.avoid)
        assert not set(opt.shots) & copied
    for opt in red.skill_options():
        assert not set(opt.shots) & copied


def test_without_unknown_tool_is_an_error(full_catalog: Catalog) -> None:
    with pytest.raises(ValueError, match="unknown tool"):
        full_catalog.without(["no_such_tool"])


def test_provider_cache_key_carries_the_exclusion() -> None:
    full = CatalogProvider(Settings(_env_file=None))
    red = CatalogProvider(Settings(_env_file=None, catalog=CatalogConfig(exclude_tools=HELD)))
    assert full.key != red.key and red.key.startswith(full.key)


# ---------------------------------------------------------------- settings / manifest / hash


def test_manifest_overrides_patch_the_config() -> None:
    run = ManifestRun(
        name="rq5-dev-regex-eng",
        config=Path("config/experiments/e1_regex.yaml"),
        mode="routing-only",
        overrides={
            "catalog.exclude_tools": HELD,
            "strategies.regex.rules_path": BASE,
            "strategies.regex.overlay_paths": [ENGINEERED],
        },
    )
    s = load_run_settings(run)
    assert s.catalog.exclude_tools == HELD
    assert s.strategies.regex.rules_path == BASE
    assert s.strategies.regex.overlay_paths == [ENGINEERED]
    assert s.strategies.regex.history_turns == 2  # the rest of the YAML is kept


def test_unknown_patch_key_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown settings patch"):
        load_settings("config/experiments/e1_regex.yaml", patches={"catlog.exclude_tools": []})


def test_config_hash_covers_overlay_and_exclusion_but_not_when_unset() -> None:
    cfg = "config/experiments/e1_regex.yaml"
    prod = load_settings(cfg)
    assert "overlay_paths" not in prod.model_dump_json(include={"strategies"})
    assert "catalog" not in prod.model_dump_json(include={"routing", "strategies", "executor"})
    hashes = {
        config_hash(load_settings(cfg, patches=p))
        for p in (
            {},
            {"strategies.regex.rules_path": BASE},
            {"strategies.regex.rules_path": BASE, "strategies.regex.overlay_paths": [ENGINEERED]},
            {"strategies.regex.rules_path": BASE, "catalog.exclude_tools": HELD},
        )
    }
    assert len(hashes) == 4


def test_config_hash_tracks_overlay_content(tmp_path: Path) -> None:
    ov = tmp_path / "ov.yaml"
    ov.write_text("rules: {}\n")
    s = load_settings(
        "config/experiments/e1_regex.yaml", patches={"strategies.regex.overlay_paths": [str(ov)]}
    )
    before = config_hash(s)
    ov.write_text("rules: {cancel_order: [{pattern: x}]}\n")
    assert config_hash(s) != before


# ---------------------------------------------------------------- table statistics


def _row(cid: str, tools: list[str], joint: float, pred: str | None) -> dict:
    return {
        "case_id": cid,
        "rep": 1,
        "expected": {"acceptable_tools": tools},
        "scores": {"joint_correct": joint, "skill_correct": joint},
        "tool": {"choice": pred},
        "error": None,
    }


def test_condition_stats_affected_and_regressions() -> None:
    held = set(HELD)
    base = {
        "a": _row("a", ["get_refund_status"], 0.0, "request_refund"),
        "b": _row("b", ["get_payment_status", "get_refund_status"], 1.0, "get_payment_status"),
        "c": _row("c", ["request_refund"], 1.0, "request_refund"),
        "d": _row("d", ["track_shipment"], 0.0, "get_order_status"),
    }
    zero = {
        "a": _row("a", ["get_refund_status"], 1.0, "get_refund_status"),
        "b": _row("b", ["get_payment_status", "get_refund_status"], 1.0, "get_refund_status"),
        "c": _row("c", ["request_refund"], 0.0, "get_refund_status"),
        "d": _row("d", ["track_shipment"], 1.0, "track_shipment"),
    }
    s = condition_stats(zero, base, held)
    assert (s["n_aff"], s["joint_aff"], s["pred_held_aff"]) == (2, 1.0, 1.0)
    assert (s["n_oth"], s["lost"], s["won"], s["stolen"]) == (2, 1, 1, 1)
    assert s["delta_oth_pp"] == 0.0
    b = condition_stats(base, None, held)
    assert b["joint_aff"] == 0.5 and "lost" not in b


def test_parse_run_names() -> None:
    assert parse_run("rq5-test_v2-sonnet-base") == RunKey("test_v2", "sonnet", "base")
    assert parse_run("rq5-dev-regex-eng") == RunKey("dev", "regex", "eng")
    assert parse_run("v2-e1-regex-routing-r1") is None


def test_effort_counts() -> None:
    cat = catalog_effort(HELD)
    assert cat["examples"] == 12 and cat["keywords"] == 15
    orig = rules_effort(Path(ORIGINAL))
    assert (orig["rules"], orig["defs"]) == (8, 2)
