"""F7 (router parts): failed steps keep their billed usage, the calibration sentinel, Jev
cache tokens."""

from __future__ import annotations

import httpx
import pytest
import respx
from router_helpers import BASE_URL, chat_completion, skill_input

from routing_study.llm import make_chat_model
from routing_study.routers.calibration import Calibration
from routing_study.routers.jev import JevRouter
from routing_study.routers.llm import LLMRouter
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import PipelineStep, StageConfig

CHAT_URL = f"{BASE_URL}/chat/completions"


def _jev(settings, **kw):
    model = "typesafe/jev-router"
    chat = make_chat_model(
        settings, model, supported_parameters=[], http_async_client=httpx.AsyncClient()
    )
    return JevRouter(chat, settings, model=model, **kw)


def _llm(settings, **kw):
    model = "anthropic/claude-haiku-4.5"
    chat = make_chat_model(
        settings, model, temperature=0, max_tokens=64, http_async_client=httpx.AsyncClient()
    )
    return LLMRouter(chat, settings, model=model, **kw)


def _single(name: str, router) -> RoutingPipeline:
    return RoutingPipeline(
        StageConfig(pipeline=[PipelineStep(strategy=name)]), {name: router}, mode="single"
    )


def _bad_request() -> httpx.Response:
    return httpx.Response(400, json={"error": {"message": "bad", "code": 400}})


# ------------------------------------------------------------------ partial usage


@respx.mock
async def test_failed_jev_step_keeps_the_cost_of_its_billed_first_call(settings, skill_options):
    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=chat_completion("no idea", cost=1e-5)),  # billed, unparsed
            _bad_request(),  # the corrective retry fails for good
        ]
    )
    res = await _single("jev", _jev(settings)).run(skill_input("x"), skill_options)
    d = res.steps[0]
    assert "400" in d.usage["error"]
    assert d.cost_usd == pytest.approx(1e-5)
    assert res.cost_usd == pytest.approx(1e-5) and res.billed_usd == pytest.approx(1e-5)
    u = d.usage
    assert u["calls"] == 1 and u["attempts"] == 2 and u["prompt_tokens"] == 100
    assert {"call_ms", "queue_ms", "retry_ms"} <= u.keys()
    assert res.routing_error is not None


@respx.mock
async def test_failed_llm_step_keeps_the_cost_of_a_cut_reply(settings, skill_options):
    body = chat_completion('{"choice": "pedi', cost=0.0042)
    body["choices"][0]["finish_reason"] = "length"  # openai raises LengthFinishReasonError
    respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=body))
    res = await _single("llm", _llm(settings)).run(skill_input("x"), skill_options)
    d = res.steps[0]
    assert d.usage["error"].startswith("LengthFinishReasonError")
    assert d.cost_usd == pytest.approx(0.0042) and res.billed_usd == pytest.approx(0.0042)
    assert d.usage["attempts"] == 1 and d.usage["completion_tokens"] == 10


@respx.mock
async def test_failed_llm_step_after_retries_records_attempts_and_timing(settings, skill_options):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(500, json={"error": {"code": 500}}))
    res = await _single("llm", _llm(settings)).run(skill_input("x"), skill_options)
    u = res.steps[0].usage
    assert u["attempts"] == settings.http_retries + 1 and res.steps[0].cost_usd == 0.0
    assert u["retry_ms"] > 0


# ------------------------------------------------------------------ calibration sentinel


def test_calibration_keeps_the_zero_confidence_sentinel():
    cal = Calibration(x=[0.0, 0.5, 1.0], y=[0.4, 0.6, 0.9])
    assert cal(0.0) == 0.0  # "do not trust" stays 0, never lifted to the map's floor
    assert cal(0.25) == pytest.approx(0.5)


@respx.mock
async def test_jev_missing_confidence_stays_zero_after_calibration(settings, skill_options):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_completion('{"choice": "pedidos_logistica"}'))
    )
    cal = {"skill": Calibration(x=[0.0, 1.0], y=[0.5, 0.95])}
    d = await _jev(settings, calibration=cal).route(skill_input("x"), skill_options)
    assert d.choice == "pedidos_logistica" and d.usage["confidence_missing"]
    assert d.confidence == 0.0 and d.usage["raw_confidence"] == 0.0


# ------------------------------------------------------------------ Jev cache tokens


@respx.mock
async def test_jev_records_cache_read_and_write_tokens(settings, skill_options):
    first = chat_completion("no idea", cost=1e-5)
    first["usage"]["prompt_tokens_details"] = {"cached_tokens": 0, "cache_write_tokens": 90}
    second = chat_completion('{"choice": "pedidos_logistica", "confidence": 0.9}', cost=1e-5)
    second["usage"]["prompt_tokens_details"] = {"cached_tokens": 90, "cache_write_tokens": 0}
    respx.post(CHAT_URL).mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )
    d = await _jev(settings).route(skill_input("x"), skill_options)
    assert d.usage["cache_read"] == 90 and d.usage["cache_write"] == 90
