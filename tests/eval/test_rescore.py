"""`study rescore` (review M2, M6; code finding 2): offline, deterministic, provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from routing_study.eval.rescore import (
    PROVENANCE,
    read_rescored,
    rescore_file,
    row_error,
)
from routing_study.eval.scorers import scorer_hash

CASE = {
    "id": "c1",
    "category": "direto",
    "customer_id": "C001",
    "turns": [{"role": "user", "content": "cadê meu pedido O0001?"}],
    "expected": {
        "acceptable_skills": ["pedidos_logistica"],
        "acceptable_tools": ["get_order_status"],
        "args": {"order_id": "O0001"},
    },
}
TOOLS = {
    "tools": [
        {
            "name": "get_order_status",
            "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}}},
            "annotations": {"readOnlyHint": True},
        }
    ]
}


def _step(strategy: str, choice: str | None, **usage: Any) -> dict[str, Any]:
    return {"strategy": strategy, "choice": choice, "confidence": 0.9, "usage": usage}


def _row(**kw: Any) -> dict[str, Any]:
    steps = kw.get("steps", [_step("llm", "pedidos_logistica")])
    resolved = kw.get("resolved_by", "llm")
    return {
        "run_name": "r",
        "config": "e5_llm_sonnet",
        "split": "dev",
        "case_id": kw.get("case_id", "c1"),
        "category": "direto",
        "rep": 1,
        "expected": {"acceptable_skills": ["stale"], "acceptable_tools": ["stale"]},
        "mode": "routing-only",
        "native": False,
        "skill": {
            "choice": "pedidos_logistica" if resolved else None,
            "resolved_by": resolved,
            "abstained": resolved is None,
            "steps": steps,
            "billed_usd": 0.001,
        },
        "tool": {
            "choice": "get_order_status",
            "resolved_by": "llm",
            "abstained": False,
            "steps": [_step("llm", "get_order_status")],
            "billed_usd": 0.0,
        },
        "calls": [],
        "outcome": None,
        "final_answer": None,
        "customer": None,
        "error": kw.get("error"),
        "scores": {"skill_correct": 0.0},
        "cost_usd": {"routing": 0.002, "agent": 0.0, "total": 0.002},
        "latency_ms": {"turn": 1.0, "routing": 1.0, "executor": None},
    }


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    data.mkdir()
    (data / "dataset_dev.jsonl").write_text(json.dumps(CASE) + "\n")
    tools = tmp_path / "tools_list.json"
    tools.write_text(json.dumps(TOOLS))
    return {"data": data, "tools": tools, "out": tmp_path / "out", "tmp": tmp_path}


def _rescore(env: dict[str, Path], rows: list[dict[str, Any]]) -> tuple[dict, list[dict]]:
    raw = env["tmp"] / "run.jsonl"
    raw.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out, _ = rescore_file(raw, env["out"], data_dir=env["data"], tools_path=env["tools"])
    return read_rescored(out)


def test_m2_rescore_recomputes_from_dataset_and_writes_provenance(env) -> None:
    prov, [row] = _rescore(env, [_row()])
    assert row["expected"] == CASE["expected"]  # the dataset, not the stale row copy
    assert row["scores"]["skill_correct"] == row["scores"]["joint_correct"] == 1.0
    assert row["raw_scores"] == {"skill_correct": 0.0}
    assert prov["scorer_hash"] == scorer_hash()
    assert len(prov["dataset"]["sha256"]) == 64 and prov["dataset"]["split"] == "dev"
    assert prov["run_git_sha"].startswith("unknown") and prov["rescore_git_sha"]
    assert prov["checks"]["expected_changed"] == 1
    assert row["cost_usd"]["billed_total"] == pytest.approx(0.001)


def test_m2_rescore_is_deterministic(env) -> None:
    raw = env["tmp"] / "run.jsonl"
    raw.write_text(json.dumps(_row()) + "\n")
    a, _ = rescore_file(raw, env["tmp"] / "a", data_dir=env["data"], tools_path=env["tools"])
    b, _ = rescore_file(raw, env["tmp"] / "b", data_dir=env["data"], tools_path=env["tools"])
    assert a.read_bytes() == b.read_bytes()


def test_m2_reports_refuse_raw_rows(env) -> None:
    raw = env["tmp"] / "raw.jsonl"
    raw.write_text(json.dumps(_row()) + "\n")
    with pytest.raises(ValueError, match="study rescore"):
        read_rescored(raw)


def test_code2_recovered_cascade_is_not_an_error_row(env) -> None:
    recovered = _row(
        steps=[_step("jev", None, error="Timeout"), _step("llm", "pedidos_logistica")],
        error="jev: Timeout",
    )
    failed = _row(
        steps=[_step("llm", None, error="Timeout")], resolved_by=None, error="llm: Timeout"
    )
    unparsed = _row(steps=[_step("llm", None, parse_fail=True)], resolved_by=None)
    crashed = {k: v for k, v in _row(error="RuntimeError: boom").items() if k != "calls"}
    assert row_error(recovered) is None
    assert row_error(failed) == "llm: Timeout"
    assert row_error(unparsed) == "llm: parse_fail"  # M4: not a scored abstention
    assert row_error(crashed) == "RuntimeError: boom"
    prov, rows = _rescore(env, [recovered, failed])
    assert [r["error"] for r in rows] == [None, "llm: Timeout"]
    assert rows[0]["raw_error"] == "jev: Timeout" and prov["checks"]["error_changed"] == 1


def test_m6_rescore_counts_rows_that_used_a_fourth_business_round(env) -> None:
    def e2e(n_calls: int, native: bool) -> dict[str, Any]:
        r = _row()
        call = {"name": "get_order_status", "args": {"order_id": "O0001"}, "status": "completed"}
        load = {"name": "load_skill", "args": {"skill": "x"}, "status": "completed"}
        r |= {"mode": "e2e", "native": native, "outcome": "answered", "final_answer": "ok"}
        r["calls"] = ([load] if native else []) + [dict(call) for _ in range(n_calls)]
        return r

    prov, _ = _rescore(env, [e2e(4, False), e2e(2, False), e2e(3, True)])
    assert prov["round4"] == {
        "routed": {"rows": 2, "round4_used": 1},
        "native": {"rows": 1, "round4_used": 0},
    }


def test_l2_list_price_uncached_cost(env) -> None:
    from routing_study.eval.rescore import list_price_usd

    row = _row()
    row["skill"]["steps"][0]["usage"] = {"prompt_tokens": 1000, "completion_tokens": 10}
    row["tool"]["steps"][0]["usage"] = {"prompt_tokens": 500, "completion_tokens": 10}
    row |= {"mode": "e2e", "tokens": {"prompt": 2000, "completion": 100, "agent_calls": 1}}
    models = {"llm": "a/m", "executor": "a/x"}
    prices = {"a/m": (1e-6, 1e-5), "a/x": (2e-6, 2e-5)}
    assert list_price_usd(row, models, prices) == pytest.approx(1500e-6 + 20e-5 + 4000e-6 + 200e-5)
    assert list_price_usd(row, models, {"a/m": (1e-6, 1e-5)}) is None  # unknown price
    assert PROVENANCE == "_provenance"


# ---------------------------------------------------------------- F7


def test_f7_paid_includes_the_shadow_strategies_billing(env) -> None:
    row = _row()
    row["skill"] |= {"billed_usd": 0.0, "shadow_billed_usd": 0.003}
    row["tool"] |= {"billed_usd": 0.0005, "shadow_billed_usd": 0.001}
    _, [out] = _rescore(env, [row])
    assert out["cost_usd"]["billed_total"] == pytest.approx(0.004)


def test_f7_list_price_uses_step_tokens_and_marks_negative_prices_na(env) -> None:
    from routing_study.eval.rescore import NA, list_price_usd

    row = _row()
    row["skill"]["steps"] = [
        _step("regex", None),
        _step("jev", None, error="Timeout"),  # failed call: no tokens, billed nothing
        _step("llm", "pedidos_logistica", prompt_tokens=1000, completion_tokens=10),
    ]
    row["tool"]["steps"][0]["usage"] = {"prompt_tokens": 500, "completion_tokens": 10}
    models = {"llm": "a/m", "jev": "openrouter/auto"}
    prices = {"a/m": (1e-6, 1e-5), "openrouter/auto": (-1.0, -1.0)}
    assert list_price_usd(row, models, prices) == pytest.approx(1500e-6 + 20e-5)
    row["skill"]["steps"][1] = _step("jev", "pedidos_logistica", prompt_tokens=10)
    assert list_price_usd(row, models, prices) == NA  # the meta-router has no list price
    row["skill"]["steps"][1] = _step("jev", "pedidos_logistica")  # a success without tokens
    assert list_price_usd(row, models, {**prices, "openrouter/auto": (1e-6, 1e-6)}) is None
