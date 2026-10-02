"""Settings / OpenRouter client fixes: final-code.md findings 5, 6, 8 and B8, B11."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from routing_study.llm import OpenRouterBodyError, _is_retryable, call_with_retry, make_chat_model
from routing_study.settings import (
    ExecutorConfig,
    LLMStrategy,
    ReasoningPrefs,
    Settings,
    load_settings,
)

BASE = "https://openrouter.test/api/v1"


def test_f5_effort_or_budget_enables_reasoning() -> None:
    assert ReasoningPrefs(effort="high").model_dump(exclude_none=True) == {
        "enabled": True,
        "effort": "high",
    }
    assert ReasoningPrefs(max_tokens=200).enabled is True
    assert ReasoningPrefs().model_dump(exclude_none=True) == {"enabled": False}
    with pytest.raises(ValidationError, match="only one"):
        ReasoningPrefs(effort="low", max_tokens=100)
    with pytest.raises(ValidationError, match="enabled=false"):
        ReasoningPrefs(enabled=False, effort="low")


def test_f5_thinking_budget_must_fit_the_output_cap() -> None:
    with pytest.raises(ValidationError, match="budget"):
        LLMStrategy(model="x/y", temperature=None, max_tokens=512, reasoning={"max_tokens": 512})
    LLMStrategy(model="x/y", temperature=None, max_tokens=512, reasoning={"max_tokens": 256})


def test_f8_temperature_with_anthropic_reasoning_is_rejected() -> None:
    with pytest.raises(ValidationError, match="temperature"):
        ExecutorConfig(model="anthropic/claude-sonnet-5", reasoning={"effort": "low"})
    ExecutorConfig(model="anthropic/claude-sonnet-5", temperature=None, reasoning={"effort": "low"})
    ExecutorConfig(model="anthropic/claude-sonnet-5", temperature=1, reasoning={"effort": "low"})
    ExecutorConfig(model="openai/x", reasoning={"effort": "low"})  # only Anthropic requires 1
    ExecutorConfig(model="anthropic/claude-sonnet-5")  # reasoning off: temperature 0 is fine


def test_f6_reasoning_sent_only_to_models_that_support_it() -> None:
    s = Settings(_env_file=None)
    off = ReasoningPrefs()
    unsupported = make_chat_model(s, "x/y", reasoning=off, supported_parameters=["temperature"])
    assert "reasoning" not in unsupported.extra_body
    supported = make_chat_model(s, "x/y", reasoning=off, supported_parameters=["reasoning"])
    assert supported.extra_body["reasoning"] == {"enabled": False}
    unknown = make_chat_model(s, "x/y", reasoning=off)  # no /models data: send as configured
    assert unknown.extra_body["reasoning"] == {"enabled": False}
    with pytest.raises(ValueError, match="does not support reasoning"):
        make_chat_model(s, "x/y", reasoning=ReasoningPrefs(effort="low"), supported_parameters=[])


def test_b11_unknown_top_level_yaml_key_is_an_error(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "e.yaml"
    cfg.write_text("strategys:\n  regex: {}\n")
    with pytest.raises(ValueError, match="strategys"):
        load_settings(cfg)
    ok = tmp_path / "ok.yaml"
    ok.write_text("routing:\n  mode: cascade\n")
    monkeypatch.setenv("SOME_UNRELATED_ENV_VAR", "1")  # env keys stay ignored
    assert load_settings(ok).routing.mode == "cascade"


def _chat_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "g",
            "object": "chat.completion",
            "created": 1,
            "model": "x/y",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


@respx.mock
async def test_b8_chat_200_with_retryable_error_body_is_retried() -> None:
    s = Settings(_env_file=None, openrouter_api_key="k", openrouter_base_url=BASE, http_retries=2)
    route = respx.post(f"{BASE}/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json={"error": {"code": 502, "message": "upstream down"}}),
            _chat_ok(),
        ]
    )
    chat = make_chat_model(s, "x/y", http_async_client=httpx.AsyncClient())
    msg = await call_with_retry(lambda: chat.ainvoke("hi"), model="x/y", settings=s)
    assert msg.content == "ok" and route.call_count == 2


@respx.mock
async def test_b8_invalid_model_error_body_is_not_retried() -> None:
    s = Settings(_env_file=None, openrouter_api_key="k", openrouter_base_url=BASE, http_retries=2)
    route = respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"error": {"code": "invalid_model", "message": "no such model"}}
        )
    )
    chat = make_chat_model(s, "x/y", http_async_client=httpx.AsyncClient())
    with pytest.raises(OpenRouterBodyError, match="invalid_model"):
        await call_with_retry(lambda: chat.ainvoke("hi"), model="x/y", settings=s)
    assert route.call_count == 1
    assert not _is_retryable(OpenRouterBodyError({"error": {"code": "invalid_model"}}))
    assert _is_retryable(OpenRouterBodyError({"error": {"message": "no code"}}))
