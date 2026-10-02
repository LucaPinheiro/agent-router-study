"""Cross-tool consistency of the mock server: no double money-back flows, no dead ends."""

from datetime import timedelta
from typing import Any

import pytest
from fastmcp import Client
from mcp_fixtures import delivered_days, find_order, large_variants, meta, pay
from mcp_server.core import DB, ORDERS, REFUNDS_BY_ORDER, RETURNS, TODAY
from test_mcp_tools import EXPECTED_BY_PROFILE


def _has_return(o: dict[str, Any]) -> bool:
    return any(r["order_id"] == o["id"] for r in RETURNS.values())


async def _call(client: Client, tool: str, customer: str, args: dict[str, Any]) -> Any:
    return await client.call_tool(tool, args, meta=meta(customer), raise_on_error=False)


# ------------------------------------------------------------------ D1


async def test_dispute_refused_when_refund_exists(client: Client) -> None:
    cid, oid = find_order(
        lambda o: (
            o["id"] in REFUNDS_BY_ORDER
            and pay(o)["method"] == "credit_card"
            and pay(o)["status"] == "approved"
        )
    )
    r = await _call(client, "dispute_charge", cid, {"order_id": oid, "reason": "duplicada"})
    assert r.is_error
    assert r.structured_content["code"] == "NOT_ELIGIBLE"
    assert r.structured_content["suggested_tool"] == "get_refund_status"


# ------------------------------------------------------------------ D2

_with_return = find_order(lambda o: _has_return(o) and o["id"] not in REFUNDS_BY_ORDER)
_with_refund = find_order(lambda o: _has_return(o) and o["id"] in REFUNDS_BY_ORDER)


@pytest.mark.parametrize(
    ("case", "suggested"),
    [(_with_return, "generate_return_label"), (_with_refund, "get_refund_status")],
)
async def test_exchange_refused_while_return_or_refund_open(
    client: Client, case: tuple[str, str], suggested: str
) -> None:
    cid, oid = case
    r = await _call(
        client,
        "create_exchange",
        cid,
        {"order_id": oid, "new_variant": "G", "sku": ORDERS[oid]["items"][0]["sku"]},
    )
    assert r.is_error
    assert r.structured_content["code"] == "NOT_ELIGIBLE"
    assert r.structured_content["suggested_tool"] == suggested


@pytest.mark.parametrize("case", [_with_return, _with_refund])
async def test_eligibility_reports_open_return_or_refund(
    client: Client, case: tuple[str, str]
) -> None:
    cid, oid = case
    r = await _call(client, "check_return_eligibility", cid, {"order_id": oid})
    assert not r.is_error
    sc = r.structured_content
    opts = {o["type"]: o["eligible"] for o in sc["options"]}
    assert opts["arrependimento"] is False and opts["devolucao_troca"] is False
    ret = next(x for x in RETURNS.values() if x["order_id"] == oid)
    assert sc["open_return_id"] == ret["id"]
    assert ret["id"] in r.content[0].text


# ------------------------------------------------------------------ D3

_fresh = find_order(
    lambda o: (
        (d := delivered_days(o)) is not None
        and d <= 7
        and not _has_return(o)
        and o["id"] not in REFUNDS_BY_ORDER
    )
)


@pytest.mark.parametrize("with_sku", [False, True])
async def test_label_for_return_created_in_same_conversation(
    client: Client, with_sku: bool
) -> None:
    cid, oid = _fresh
    args: dict[str, Any] = {"order_id": oid, "reason": "arrependimento"}
    if with_sku:
        args["sku"] = ORDERS[oid]["items"][0]["sku"]
    created = await _call(client, "create_return_request", cid, args)
    assert not created.is_error, created.content
    rid = created.structured_content["return_id"]
    r = await _call(client, "generate_return_label", cid, {"return_id": rid.lower()})
    assert not r.is_error, r.content
    sc = r.structured_content
    assert sc["return_id"] == rid and sc["order_id"] == oid
    assert sc["post_by"] == created.structured_content["post_by"]


async def test_minted_return_id_is_bound_to_customer(client: Client) -> None:
    cid, oid = _fresh
    created = await _call(
        client, "create_return_request", cid, {"order_id": oid, "reason": "arrependimento"}
    )
    other = next(c for c in ("C001", "C002", "C003") if c != cid)
    r = await _call(
        client,
        "generate_return_label",
        other,
        {"return_id": created.structured_content["return_id"]},
    )
    assert r.is_error and r.structured_content["code"] == "NOT_FOUND"


async def test_unknown_return_id_does_not_loop_to_create(client: Client) -> None:
    cid, _ = _fresh
    r = await _call(client, "generate_return_label", cid, {"return_id": "DEV-00000000"})
    assert r.is_error and r.structured_content["code"] == "NOT_FOUND"
    assert r.structured_content["suggested_tool"] != "create_return_request"


async def test_label_by_order_without_return_explains_return_id(client: Client) -> None:
    cid, oid = _fresh
    r = await _call(client, "generate_return_label", cid, {"order_id": oid})
    assert r.is_error and r.structured_content["code"] == "NOT_ELIGIBLE"
    assert "return_id" in r.structured_content["message"]
    # D3: the order_id path must not send the agent back to create_return_request either
    # (writes don't persist, so that pair loops forever)
    assert r.structured_content.get("suggested_tool") != "create_return_request"


# ------------------------------------------------------------------ D4

_ADDRESS = {
    "street": "Rua Bahia",
    "number": "90",
    "neighborhood": "Higienópolis",
    "city": "São Paulo",
    "state": "SP",
    "postal_code": "01244-000",
}


def _variants(tool: str, oid: str) -> list[dict[str, Any]]:
    """Plausible argument sets a model could send for `tool` about order `oid` (the large
    profile's new tools included, for the order's customer)."""
    if (new := large_variants(tool, ORDERS[oid]["customer_id"], oid)) is not None:
        return new
    sku = ORDERS[oid]["items"][0]["sku"]
    o = {"order_id": oid}
    return {
        "get_customer_profile": [{}],
        "search_help_center": [{"query": "prazo para devolver"}],
        "escalate_to_human": [{"reason": "cliente pediu ajuda", **o}],
        "update_delivery_address": [{**o, **_ADDRESS}],
        "reschedule_delivery": [{**o, "new_date": (TODAY + timedelta(days=3)).isoformat()}],
        "request_refund": [{**o, "reason": "quero meu dinheiro"}],
        "dispute_charge": [{**o, "reason": r} for r in ("nao_reconhecida", "duplicada")],
        "create_return_request": [
            {**o, "sku": sku, "reason": r} for r in ("arrependimento", "defeito")
        ],
        "create_exchange": [{**o, "sku": sku, "new_variant": "G"}],
        "open_warranty_claim": [{**o, "sku": sku, "defect_description": "parou de ligar"}],
    }.get(tool, [o])


_ORDER_CASES = [(o["customer_id"], o["id"]) for o in DB["orders"]]


async def test_every_suggested_tool_can_succeed(client: Client, profile: str) -> None:
    tools = sorted(set().union(*EXPECTED_BY_PROFILE[profile].values()))
    dead_ends: list[str] = []
    for cid, oid in _ORDER_CASES:
        for tool in tools:
            for args in _variants(tool, oid):
                r = await _call(client, tool, cid, args)
                nxt = r.structured_content["suggested_tool"] if r.is_error else None
                if not nxt:
                    continue
                results = [await _call(client, nxt, cid, a) for a in _variants(nxt, oid)]
                if all(x.is_error for x in results):
                    dead_ends.append(
                        f"{tool}({oid}) -> {nxt}: {results[0].structured_content['code']}"
                    )
    assert not dead_ends, "\n".join(sorted(set(dead_ends)))


async def test_error_suggestions_outside_order_scope_can_succeed(client: Client) -> None:
    for tool, customer, args in [
        ("get_order_status", "C001", {"order_id": "O9999"}),
        ("get_customer_profile", None, {}),
        ("get_customer_profile", "C999", {}),
        ("search_help_center", "C001", {"query": "xablau zzzqqq"}),
        ("generate_return_label", "C001", {"return_id": "DEV-00000000"}),
    ]:
        r = await _call(client, tool, customer, args)  # type: ignore[arg-type]
        assert r.is_error
        nxt = r.structured_content["suggested_tool"]
        if nxt is None:
            continue
        follow_args = {"reason": "cliente pediu ajuda"} if nxt == "escalate_to_human" else {}
        follow = await _call(client, nxt, customer, follow_args)  # type: ignore[arg-type]
        assert not follow.is_error, (tool, nxt, follow.content)


# ------------------------------------------------------------------ F5


async def test_read_tools_never_suggest_an_irreversible_action(client: Client) -> None:
    """A read tool's refusal points to another read or to escalation, never to a destructive
    write (cancel_order, dispute_charge): the agent must not act on a lookup's hint."""
    listed = {t.name: t.annotations for t in await client.list_tools()}
    reads = sorted(n for n, a in listed.items() if a and a.read_only_hint)
    destructive = {n for n, a in listed.items() if a and a.destructive_hint}
    assert reads and destructive
    bad: list[str] = []
    for cid, oid in _ORDER_CASES:
        for tool in reads:
            for args in _variants(tool, oid):
                r = await _call(client, tool, cid, args)
                nxt = r.structured_content["suggested_tool"] if r.is_error else None
                if nxt in destructive:
                    bad.append(f"{tool}({oid}) -> {nxt}")
    assert not bad, "\n".join(bad)


async def test_missing_refund_or_return_is_not_eligible_but_foreign_order_is_not_found(
    client: Client,
) -> None:
    cid, oid = find_order(lambda o: o["id"] not in REFUNDS_BY_ORDER)
    r = await _call(client, "get_refund_status", cid, {"order_id": oid})
    assert r.is_error and r.structured_content["code"] == "NOT_ELIGIBLE"
    other = next(o["id"] for o in DB["orders"] if o["customer_id"] != cid)
    for tool in ("get_refund_status", "generate_return_label"):
        r = await _call(client, tool, cid, {"order_id": other})
        assert r.is_error and r.structured_content["code"] == "NOT_FOUND", tool
