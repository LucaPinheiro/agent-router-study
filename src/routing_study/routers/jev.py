"""Jev router: `typesafe/jev-router` via OpenRouter, used as a classifier.

jev-router is a model meta-router with `supported_parameters: []`: no structured output,
temperature or seed. The prompt asks for `{"choice", "confidence"}` JSON; a tolerant parser
reads it, with `parse_retries` corrective retries. The model actually served is recorded in
`usage["served_model"]`; a final parse failure abstains with `usage["parse_fail"] = True`.
"""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from routing_study.llm import RetryStats, call_with_retry, extract_call_usage
from routing_study.routers.base import ABSTAIN, RouteDecision, RouteOption, RoutingInput
from routing_study.routers.common import BaseRouter, ResponseCache, clamp01, normalize
from routing_study.routers.llm import build_messages
from routing_study.settings import Settings

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_OBJ = re.compile(r"\{.*?\}", re.DOTALL)
_CHOICE = re.compile(r"""["']?choice["']?\s*[:=]\s*["']?([\w\-.]+)""", re.IGNORECASE)
_CONF = re.compile(r"""["']?confidence["']?\s*[:=]\s*["']?([0-9]*\.?[0-9]+)\s*(%)?""",
                   re.IGNORECASE)


def _match_id(value: str, valid: list[str]) -> str | None:
    v = value.strip().strip("`'\"").strip()
    if v in valid:
        return v
    low = {normalize(x): x for x in valid}
    return low.get(normalize(v))


def _to_conf(value: Any, percent: bool = False) -> float | None:
    try:
        f = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    if percent or (1.0 < f <= 100.0):
        f /= 100.0
    return clamp01(f)


def parse_choice(text: str, valid: list[str]) -> tuple[str | None, float | None]:
    """Tolerant parse of `{"choice": ..., "confidence": ...}`. Returns (choice, confidence).

    Handles code fences, surrounding prose, single quotes, percent confidences, case/accents
    in ids, and a bare option id. `choice` is None when no valid id can be recovered.
    """
    if not text:
        return None, None
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for chunk in candidates:
        for m in _OBJ.finditer(chunk):
            blob = m.group(0)
            for attempt in (blob, blob.replace("'", '"')):
                try:
                    obj = json.loads(attempt)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "choice" in obj:
                    choice = _match_id(str(obj["choice"]), valid)
                    if choice is not None:
                        return choice, _to_conf(obj.get("confidence"))
    m = _CHOICE.search(text)
    if m:
        choice = _match_id(m.group(1), valid)
        if choice is not None:
            c = _CONF.search(text)
            return choice, (_to_conf(c.group(1), bool(c.group(2))) if c else None)
    return _match_id(text, valid), None


class JevRouter(BaseRouter):
    name: ClassVar[str] = "jev"
    paid: ClassVar[bool] = True

    def __init__(
        self,
        chat: Any,
        settings: Settings,
        *,
        model: str,
        parse_retries: int = 1,
        history_turns: int = 4,
        allow_abstain: bool = False,
        cache: ResponseCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.chat = chat
        self.settings = settings
        self._model = model
        self.parse_retries = parse_retries
        self.history_turns = history_turns
        self.allow_abstain = allow_abstain

    @property
    def model(self) -> str | None:
        return self._model

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        valid = [o.id for o in options] + ([ABSTAIN] if self.allow_abstain else [])
        messages: list[BaseMessage] = build_messages(
            inp, options, history_turns=self.history_turns,
            allow_abstain=self.allow_abstain, json_reply=True, model=self._model,
        )
        cost = 0.0
        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        served: list[str | None] = []
        providers: list[str | None] = []
        attempts = 0
        choice: str | None = None
        conf: float | None = None
        raw_text = ""
        for call in range(self.parse_retries + 1):
            stats = RetryStats()
            msg: AIMessage = await call_with_retry(
                lambda msgs=list(messages): self.chat.ainvoke(msgs),
                model=self._model, settings=self.settings, stats=stats,
            )
            attempts += stats.attempts
            u = extract_call_usage(msg)
            cost += u["cost_usd"]
            for k in tokens:
                tokens[k] += int(u.get(k) or 0)
            served.append(u.get("served_model"))
            providers.append(u.get("provider"))
            raw_text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            choice, conf = parse_choice(raw_text, valid)
            if choice is not None:
                break
            if call < self.parse_retries:
                messages = [*messages, AIMessage(raw_text), HumanMessage(
                    "Invalid answer. Reply with ONLY the JSON object "
                    '{"choice": "<option id>", "confidence": <0..1>} using one of: '
                    + ", ".join(valid)
                )]
        usage: dict[str, Any] = {
            "calls": len(served),
            "attempts": attempts,
            **tokens,
            "served_model": served[-1],
            "served_models": served,
            "provider": providers[-1],
            "parse_retries_used": len(served) - 1,
        }
        if choice is None:
            usage["parse_fail"] = True
            usage["raw_output"] = raw_text[:300]
            return RouteDecision(choice=None, confidence=0.0, strategy=self.name,
                                 cost_usd=cost, usage=usage)
        if conf is None:
            usage["confidence_missing"] = True
            conf = 0.5
        if choice == ABSTAIN:
            return RouteDecision(choice=None, confidence=0.0, candidates=[(ABSTAIN, conf)],
                                 strategy=self.name, cost_usd=cost, usage=usage)
        return RouteDecision(choice=choice, confidence=conf, candidates=[(choice, conf)],
                             strategy=self.name, cost_usd=cost, usage=usage)
