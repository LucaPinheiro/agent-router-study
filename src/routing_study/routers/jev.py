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
from routing_study.routers.common import BaseRouter, ResponseCache, normalize
from routing_study.routers.llm import build_messages, chat_params, ranked_candidates, rendered
from routing_study.settings import Settings

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_OBJ = re.compile(r"\{.*?\}", re.DOTALL)
_OUTER = re.compile(r"\{.*\}", re.DOTALL)  # whole object, so a nested `ranking` parses
_CHOICE = re.compile(r"""["']?choice["']?\s*[:=]\s*["']?([\w\-.]+)""", re.IGNORECASE)
_CONF = re.compile(
    r"""["']?confidence["']?\s*[:=]\s*["']?([0-9]*\.?[0-9]+)\s*(%)?""", re.IGNORECASE
)


_CORRECTION = (
    "Invalid answer. Reply with ONLY the JSON object "
    '{"choice": "<option id>", "confidence": <0..1>} using one of: '
)


def _match_id(value: str, valid: list[str]) -> str | None:
    v = value.strip().strip("`'\"").strip()
    if v in valid:
        return v
    low = {normalize(x): x for x in valid}
    return low.get(normalize(v))


def _to_conf(value: Any, percent: bool = False) -> float | None:
    """A probability in [0, 1]; an explicit percent ("85%") is converted. Anything else out
    of range (e.g. a bare 90) is invalid -> None, never silently rescaled or clamped."""
    text = str(value).strip()
    try:
        f = float(text.rstrip("%"))
    except (TypeError, ValueError):
        return None
    if percent or text.endswith("%"):
        f /= 100.0
    return f if 0.0 <= f <= 1.0 else None


def _choice_object(text: str, valid: list[str]) -> tuple[str, dict[str, Any]] | None:
    """First JSON object in `text` with a valid `choice`: (matched id, object)."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    decoder = json.JSONDecoder()
    for chunk in candidates:
        # exact JSON objects first (a greedy regex would swallow trailing "{...}" prose and
        # lose the nested ranking), then the tolerant regex blobs
        for i in (i for i, c in enumerate(chunk) if c == "{"):
            try:
                obj, _ = decoder.raw_decode(chunk, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "choice" in obj:
                choice = _match_id(str(obj["choice"]), valid)
                if choice is not None:
                    return choice, obj
        for m in [*_OUTER.finditer(chunk), *_OBJ.finditer(chunk)]:
            blob = m.group(0)
            for attempt in (blob, blob.replace("'", '"')):
                try:
                    obj = json.loads(attempt)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "choice" in obj:
                    choice = _match_id(str(obj["choice"]), valid)
                    if choice is not None:
                        return choice, obj
    return None


def parse_ranking(text: str, valid: list[str]) -> list[tuple[str, float]]:
    """`ranking` of the reply object as [(id, confidence)]; [] when absent or malformed."""
    found = _choice_object(text or "", valid)
    raw = found[1].get("ranking") if found else None
    out: list[tuple[str, float]] = []
    for item in raw if isinstance(raw, list) else []:
        cid = _match_id(str(item.get("id", "")), valid) if isinstance(item, dict) else None
        if cid is not None:
            out.append((cid, _to_conf(item.get("confidence")) or 0.0))
    return out


def parse_reply(text: str, valid: list[str]) -> tuple[str | None, float | None, Any]:
    """Tolerant parse of `{"choice": ..., "confidence": ...}` -> (choice, confidence, raw
    confidence as replied). `confidence` is None when missing or outside [0, 1].

    Handles code fences, surrounding prose, single quotes, percent confidences, case/accents
    in ids, and a bare option id. `choice` is None when no valid id can be recovered.
    """
    if not text:
        return None, None, None
    found = _choice_object(text, valid)
    if found:
        raw = found[1].get("confidence")
        return found[0], _to_conf(raw) if raw is not None else None, raw
    m = _CHOICE.search(text)
    if m:
        choice = _match_id(m.group(1), valid)
        if choice is not None:
            c = _CONF.search(text)
            if c is None:
                return choice, None, None
            return choice, _to_conf(c.group(1), bool(c.group(2))), c.group(1) + (c.group(2) or "")
    return _match_id(text, valid), None, None


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

    def _messages(self, inp: RoutingInput, options: list[RouteOption]) -> list[BaseMessage]:
        return build_messages(
            inp,
            options,
            history_turns=self.history_turns,
            allow_abstain=self.allow_abstain,
            json_reply=True,
            model=self._model,
        )

    def cache_params(self, inp: RoutingInput, options: list[RouteOption]) -> dict[str, Any]:
        return {
            "model": self._model,
            "history_turns": self.history_turns,
            "allow_abstain": self.allow_abstain,
            "parse_retries": self.parse_retries,
            "chat": chat_params(self.chat),
            "prompt": rendered(self._messages(inp, options)),
            "correction": _CORRECTION,
        }

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        valid = [o.id for o in options] + ([ABSTAIN] if self.allow_abstain else [])
        messages = self._messages(inp, options)
        cost = 0.0
        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        served: list[str | None] = []
        providers: list[str | None] = []
        attempts = 0
        queue_ms = retry_ms = 0.0
        choice: str | None = None
        conf: float | None = None
        conf_raw: Any = None
        raw_text = ""
        for call in range(self.parse_retries + 1):
            stats = RetryStats()
            msg: AIMessage = await call_with_retry(
                lambda msgs=list(messages): self.chat.ainvoke(msgs),
                model=self._model,
                settings=self.settings,
                stats=stats,
            )
            attempts += stats.attempts
            queue_ms += stats.queue_ms
            retry_ms += stats.retry_ms
            u = extract_call_usage(msg)
            cost += u["cost_usd"]
            for k in tokens:
                tokens[k] += int(u.get(k) or 0)
            served.append(u.get("served_model"))
            providers.append(u.get("provider"))
            raw_text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            choice, conf, conf_raw = parse_reply(raw_text, valid)
            if choice is not None:
                break
            if call < self.parse_retries:
                messages = [
                    *messages,
                    AIMessage(raw_text),
                    HumanMessage(_CORRECTION + ", ".join(valid)),
                ]
        usage: dict[str, Any] = {
            "calls": len(served),
            "attempts": attempts,
            "queue_ms": queue_ms,
            "retry_ms": retry_ms,
            **tokens,
            "served_model": served[-1],
            "served_models": served,
            "provider": providers[-1],
            "parse_retries_used": len(served) - 1,
        }
        if choice is None:
            usage["parse_fail"] = True
            usage["raw_output"] = raw_text[:300]
            return RouteDecision(
                choice=None, confidence=0.0, strategy=self.name, cost_usd=cost, usage=usage
            )
        usage["confidence_raw"] = conf_raw
        if conf is None:  # parse_fail-lite: keep the choice, trust nothing about it
            usage["confidence_missing" if conf_raw is None else "confidence_invalid"] = True
            conf = 0.0
        if choice == ABSTAIN:
            return RouteDecision(
                choice=None,
                confidence=0.0,
                candidates=[(ABSTAIN, conf)],
                strategy=self.name,
                cost_usd=cost,
                usage=usage,
            )
        candidates = ranked_candidates(
            choice, conf, parse_ranking(raw_text, valid), [o.id for o in options]
        )
        return RouteDecision(
            choice=choice,
            confidence=conf,
            candidates=candidates,
            strategy=self.name,
            cost_usd=cost,
            usage=usage,
        )
