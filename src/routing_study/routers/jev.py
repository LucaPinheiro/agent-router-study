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
from routing_study.prompts.routers import parse_variant, templates
from routing_study.routers.base import ABSTAIN, RouteDecision, RouteOption, RoutingInput
from routing_study.routers.calibration import Calibration
from routing_study.routers.common import (
    BaseRouter,
    ResponseCache,
    attach_partial_usage,
    normalize,
)
from routing_study.routers.llm import (
    _json_shape,
    build_messages,
    chat_params,
    prompt_chars,
    ranked_candidates,
    rendered,
)
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


def _ranking_object(text: str) -> dict[str, Any] | None:
    """First JSON object in `text` (fenced or not) with a list `ranking`."""
    decoder = json.JSONDecoder()
    for chunk in [m.group(1) for m in _FENCE.finditer(text)] + [text]:
        for i in (i for i, c in enumerate(chunk) if c == "{"):
            try:
                obj, _ = decoder.raw_decode(chunk, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("ranking"), list):
                return obj
    return None


def parse_ranked_reply(
    text: str, valid: list[str]
) -> tuple[str | None, float | None, Any, list[tuple[str, float]]]:
    """Top-k reply of the P6 / P6c variants: `{"ranking": [id, ...], "confidence": p}` or
    `{"ranking": [{"id", "score"}, ...]}` -> (choice, confidence, raw confidence, others).
    Falls back to the `{"choice", ...}` shape (a model may ignore the format)."""
    obj = _ranking_object(text or "")
    if obj is None:
        choice, conf, raw = parse_reply(text, valid)
        if choice is not None:
            return choice, conf, raw, parse_ranking(text, valid)
        return _ranking_fallback(text or "", valid)
    items: list[tuple[str, Any]] = []
    for it in obj["ranking"]:
        if isinstance(it, dict):
            cid, score = _match_id(str(it.get("id", "")), valid), it.get("score")
        else:
            cid, score = _match_id(str(it), valid), None
        if cid is not None and cid not in {c for c, _ in items}:
            items.append((cid, score))
    if not items:
        return None, None, None, []
    raw = obj.get("confidence", items[0][1])
    conf = _to_conf(raw) if raw is not None else None
    return items[0][0], conf, raw, [(c, _to_conf(v) or 0.0) for c, v in items[1:]]


def _ids_after_ranking(text: str, valid: list[str]) -> list[str]:
    """Valid ids written after a `ranking` key, in order, deduplicated (regex, so a cut or
    unquoted ranking still yields them)."""
    key = re.search(r"""["']?ranking["']?\s*[:=]""", text, re.IGNORECASE)
    if key is None or not valid:
        return []
    alts = "|".join(re.escape(v) for v in sorted(valid, key=len, reverse=True))
    ids: list[str] = []
    for m in re.finditer(rf"(?<![\w.\-])({alts})(?![\w.\-])", text[key.end() :]):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def _ranking_fallback(
    text: str, valid: list[str]
) -> tuple[str | None, float | None, Any, list[tuple[str, float]]]:
    """Malformed ranking (cut mid-object, unquoted ids, `ranking: [...]` prose): its ids in
    order (first = choice) and the confidence if one is written."""
    ids = _ids_after_ranking(text, valid)
    if not ids:
        return None, None, None, []
    c = _CONF.search(text)
    raw = (c.group(1) + (c.group(2) or "")) if c else None
    conf = _to_conf(c.group(1), bool(c.group(2))) if c else None
    return ids[0], conf, raw, [(i, 0.0) for i in ids[1:]]


def parse_ranking(text: str, valid: list[str]) -> list[tuple[str, float]]:
    """`ranking` of the reply object as [(id, confidence)]; [] when absent or malformed."""
    found = _choice_object(text or "", valid)
    raw = found[1].get("ranking") if found else None
    out: list[tuple[str, float]] = []
    for item in raw if isinstance(raw, list) else []:
        cid = _match_id(str(item.get("id", "")), valid) if isinstance(item, dict) else None
        if cid is not None:
            out.append((cid, _to_conf(item.get("confidence")) or 0.0))
    if not out and found is None:  # no parseable object: the ids a regex can still read
        out = [(i, 0.0) for i in _ids_after_ranking(text or "", valid)]
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
        prompt_variant: str = "P0",
        calibration: dict[str, Calibration] | None = None,
    ) -> None:
        super().__init__(cache=cache, calibration=calibration)
        self.prompt_variant = prompt_variant
        self.spec = parse_variant(prompt_variant)
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
            spec=self.spec,
        )

    def _correction(self, inp: RoutingInput, options: list[RouteOption]) -> str:
        """Corrective retry text. Skill stage: `{choice, confidence}` + the valid ids (the
        pre-study text, cache keys unchanged). Tool stage: the variant's full reply shape, so
        the retry keeps asking for the ranking the host exposes."""
        valid = [o.id for o in options] + ([ABSTAIN] if self.allow_abstain else [])
        if inp.level != "tool":
            return _CORRECTION + ", ".join(valid)
        ids = [o.id for o in options]
        t = templates(self.spec.language)
        return "Invalid answer. " + _json_shape("tool", ids, self.allow_abstain, self.spec, t)

    def cache_params(self, inp: RoutingInput, options: list[RouteOption]) -> dict[str, Any]:
        correction = _CORRECTION if inp.level != "tool" else self._correction(inp, options)
        return {
            "model": self._model,
            "history_turns": self.history_turns,
            "allow_abstain": self.allow_abstain,
            "parse_retries": self.parse_retries,
            "chat": chat_params(self.chat),
            "prompt": rendered(self._messages(inp, options)),
            "correction": correction,
        }

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        valid = [o.id for o in options] + ([ABSTAIN] if self.allow_abstain else [])
        messages = self._messages(inp, options)
        static_chars, dynamic_chars = prompt_chars(messages)
        cost = 0.0
        tokens = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "cache_read": 0,  # OpenRouter usage.prompt_tokens_details (cached / cache write)
            "cache_write": 0,
        }
        served: list[str | None] = []
        providers: list[str | None] = []
        attempts = 0
        call_ms = queue_ms = retry_ms = 0.0
        choice: str | None = None
        conf: float | None = None
        conf_raw: Any = None
        others: list[tuple[str, float]] = []
        raw_text = ""
        ranked_reply = inp.level == "tool" and self.spec.output != "verbose"
        for call in range(self.parse_retries + 1):
            stats = RetryStats()
            try:
                msg: AIMessage = await call_with_retry(
                    lambda msgs=list(messages): self.chat.ainvoke(msgs),
                    model=self._model,
                    settings=self.settings,
                    stats=stats,
                    provider=getattr(self.chat, "provider_name", None),
                )
            except Exception as exc:  # keep what the earlier (billed) calls cost
                billed = getattr(exc, "call_usage", None) or {}
                partial = {k: v + int(billed.get(k) or 0) for k, v in tokens.items()}
                attach_partial_usage(
                    exc,
                    cost + float(billed.get("cost_usd") or 0.0),
                    {
                        "calls": len(served) + (1 if billed else 0),
                        "attempts": attempts + stats.attempts,
                        "call_ms": call_ms + stats.call_ms,
                        "queue_ms": queue_ms + stats.queue_ms,
                        "retry_ms": retry_ms + stats.retry_ms,
                        **partial,
                        "served_models": served,
                        "static_chars": static_chars,
                        "dynamic_chars": dynamic_chars,
                    },
                )
                raise
            attempts += stats.attempts
            call_ms += stats.call_ms
            queue_ms += stats.queue_ms
            retry_ms += stats.retry_ms
            u = extract_call_usage(msg)
            cost += u["cost_usd"]
            for k in tokens:
                tokens[k] += int(u.get(k) or 0)
            served.append(u.get("served_model"))
            providers.append(u.get("provider"))
            raw_text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            if ranked_reply:
                choice, conf, conf_raw, others = parse_ranked_reply(raw_text, valid)
            else:
                choice, conf, conf_raw = parse_reply(raw_text, valid)
                others = parse_ranking(raw_text, valid) if choice else []
            if choice is not None:
                break
            if call < self.parse_retries:
                messages = [
                    *messages,
                    AIMessage(raw_text),
                    HumanMessage(self._correction(inp, options)),
                ]
        usage: dict[str, Any] = {
            "calls": len(served),
            "attempts": attempts,
            "call_ms": call_ms,
            "queue_ms": queue_ms,
            "retry_ms": retry_ms,
            **tokens,
            "served_model": served[-1],
            "served_models": served,
            "provider": providers[-1],
            "parse_retries_used": len(served) - 1,
            "static_chars": static_chars,
            "dynamic_chars": dynamic_chars,
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
        candidates = ranked_candidates(choice, conf, others, [o.id for o in options])
        return RouteDecision(
            choice=choice,
            confidence=conf,
            candidates=candidates,
            strategy=self.name,
            cost_usd=cost,
            usage=usage,
        )
