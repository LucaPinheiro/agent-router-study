"""LLM router: structured output with an `enum` of option ids + a confidence that is either
self-reported (`confidence` field) or the probability of the choice tokens (`logprob`).

One class serves every LLM strategy (`llm` and each `llm_<suffix>`): the strategy name is an
instance attribute, the model/provider come from that strategy's config block."""

from __future__ import annotations

import math
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, Field, ValidationError, create_model

from routing_study.llm import RetryStats, call_with_retry, extract_call_usage, structured_runnable
from routing_study.prompts import escape_data
from routing_study.prompts.routers import PromptSpec, parse_variant, templates
from routing_study.routers.base import (
    ABSTAIN,
    GLOBAL_OPTION,
    RouteDecision,
    RouteOption,
    RoutingInput,
)
from routing_study.routers.calibration import Calibration
from routing_study.routers.common import (
    BaseRouter,
    ResponseCache,
    attach_partial_usage,
    clamp01,
    history_text,
)
from routing_study.settings import Settings


def _json_shape(
    level: str, ids: list[str], allow_abstain: bool, spec: PromptSpec, t: dict[str, Any]
) -> str:
    """The reply object spelled out for JSON-mode replies (Jev, logprob confidence)."""
    enum = "[" + ", ".join(f'"{i}"' for i in ids) + (f', "{ABSTAIN}"' if allow_abstain else "")
    head = f'"rationale": "{t["rationale_value"]}", ' if spec.rationale else ""
    if level == "tool" and spec.output == "compact":
        body = f'"ranking": [<up to {spec.rank_k} of {enum}], best first>], '
        body += '"confidence": <number 0..1>'
    elif level == "tool" and spec.output == "scored":
        body = f'"ranking": [{{"id": <one of {enum}]>, "score": <number 0..1>}}, ...'
        body += f" up to {spec.rank_k}, best first]"
    else:
        body = f'"choice": <one of {enum}]>, "confidence": <number 0..1>'
        if level == "tool":
            body += ', "ranking": [{"id": <option id>, "confidence": <number 0..1>}, ...]'
    return t["json_intro"] + "{" + head + body + "}"


def _guide(options: list[RouteOption], t: dict[str, Any]) -> list[str]:
    ids = {o.id for o in options}
    return [
        t["guide_line"].format(id=o.id, text=escape_data(text))
        for o in options
        for text, targets in o.avoid
        if ids.intersection(targets)
    ]


def _shots(options: list[RouteOption], k: int) -> dict[str, list[str]]:
    """First `k` catalog shots per option (shown as demonstrations, not inline examples)."""
    return {o.id: o.shots[:k] for o in options}


def build_messages(
    inp: RoutingInput,
    options: list[RouteOption],
    *,
    history_turns: int,
    allow_abstain: bool,
    json_reply: bool,
    model: str = "",
    spec: PromptSpec | None = None,
) -> list[BaseMessage]:
    """Routing prompt shared by the LLM and Jev routers, static -> dynamic: rules, options,
    guide and demonstrations (a cache breakpoint on Anthropic models), then loaded skill +
    history + message. `spec` = the prompt variant (default P0)."""
    spec = spec or PromptSpec()
    t = templates(spec.language)
    shots = _shots(options, spec.shots) if spec.shots else {}
    lines = []
    for o in options:  # option text comes from the MCP server: data, escaped like the rest
        shown = [e for e in o.examples[:5] if e not in shots.get(o.id, [])]
        ex = escape_data("; ".join(shown))
        lines.append(
            f"- id: {o.id}\n  description: {escape_data(o.description)}"
            + (f"\n  examples: {ex}" if ex else "")
        )
    level = inp.level
    rules = [t["role"].format(noun=t["noun"][level]), t["match"]]
    ids = [o.id for o in options]
    if spec.scope and (level == "tool" or GLOBAL_OPTION in ids):
        rules.append(t["scope"][level].format(global_id=GLOBAL_OPTION))
    rules += [t["confidence"], t["data"]]
    if spec.rationale:
        rules.append(t["rationale"])
    if allow_abstain:
        rules.append(t["abstain"].format(abstain=ABSTAIN))
    if level == "tool":  # the host exposes the top-k tools: rank the alternatives
        rules.append(t["rank"][spec.output].format(k=min(spec.rank_k, len(options))))
    if json_reply:
        rules.append(_json_shape(level, ids, allow_abstain, spec, t))
    system = "\n".join(rules) + "\n\n<options>\n" + "\n".join(lines) + "\n</options>"
    guide = _guide(options, t) if spec.guide else []
    if guide:
        system += "\n\n<guide>\n" + t["guide_intro"] + "\n" + "\n".join(guide) + "\n</guide>"
    if shots:
        demo = [  # round-robin over options, so ids do not cluster
            f'- "{escape_data(s[i])}" -> {oid}'
            for i in range(spec.shots)
            for oid, s in shots.items()
            if i < len(s)
        ]
        system += "\n\n<examples>\n" + t["shots_intro"] + "\n" + "\n".join(demo) + "\n</examples>"
    user = f"<message>\n{escape_data(inp.message)}\n</message>"
    hist = history_text(inp, history_turns)
    if hist:
        user = f"<history>\n{hist}\n</history>\n{user}"
    if inp.loaded_skill:
        user = f"<loaded_skill>{escape_data(inp.loaded_skill)}</loaded_skill>\n{user}"
    if "anthropic" in model:  # OpenRouter `anthropic/…` or Bedrock `….anthropic.…`
        block = {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        return [SystemMessage([block]), HumanMessage(user)]
    return [SystemMessage(system), HumanMessage(user)]


def prompt_chars(messages: list[BaseMessage]) -> tuple[int, int]:
    """(static, dynamic) characters: system prefix vs the per-request user message."""

    def size(m: BaseMessage) -> int:
        c = m.content
        return len(c) if isinstance(c, str) else sum(len(b.get("text", "")) for b in c)  # type: ignore[union-attr]

    return size(messages[0]), sum(size(m) for m in messages[1:])


def choice_schema(
    option_ids: list[str],
    ranked_ids: list[str] | None = None,
    spec: PromptSpec | None = None,
) -> type[BaseModel]:
    """`ranked_ids` (tool level) adds the ranking in the variant's output format."""
    spec = spec or PromptSpec()
    fields: dict[str, Any] = {}
    if spec.rationale:
        fields["rationale"] = (str, Field(description="At most 15 words: what the user wants"))
    conf = (float, Field(description="Probability (0..1) that the choice is correct"))
    ids_t = Literal[tuple(option_ids)]
    if ranked_ids and spec.output == "compact":
        k = min(spec.rank_k, len(ranked_ids))
        fields["ranking"] = (
            list[ids_t],  # type: ignore[valid-type]
            Field(description=f"Up to {k} option ids, best first", min_length=1, max_length=k),
        )
        fields["confidence"] = (float, Field(description="Probability that the first is correct"))
        return create_model("RouteRanking", **fields)
    if ranked_ids and spec.output == "scored":
        k = min(spec.rank_k, len(ranked_ids))
        item = create_model(
            "ScoredOption",
            id=(ids_t, Field(description="Option id")),
            score=(float, Field(description="Probability (0..1) that it is correct")),
        )
        fields["ranking"] = (
            list[item],  # type: ignore[valid-type]
            Field(description=f"Up to {k} options, best first", min_length=1, max_length=k),
        )
        return create_model("RouteScored", **fields)
    fields["choice"] = (ids_t, Field(description="Chosen option id"))
    fields["confidence"] = conf
    if ranked_ids:
        alt = create_model(
            "RankedOption",
            id=(Literal[tuple(ranked_ids)], Field(description="Option id")),
            confidence=(float, Field(description="Probability (0..1) that it is correct")),
        )
        fields["ranking"] = (list[alt], Field(description="Other options, best first"))  # type: ignore[valid-type]
    return create_model("RouteChoice", **fields)


def trim_ranking(reply: Any, k: int) -> Any:
    """A top-k ranking longer than k (providers that ignore maxItems) is cut, not failed."""
    if isinstance(reply, dict) and "choice" not in reply and isinstance(reply.get("ranking"), list):
        return {**reply, "ranking": reply["ranking"][:k]}
    return reply


def read_choice(parsed: BaseModel) -> tuple[str, float, list[tuple[str, float]]] | None:
    """(choice, confidence, [(other id, confidence)]) of any reply shape; None if empty.
    A compact ranking has no score for the alternatives: 0.0 (order is what counts)."""
    ranking = getattr(parsed, "ranking", None) or []
    if hasattr(parsed, "choice"):
        return parsed.choice, parsed.confidence, [(r.id, r.confidence) for r in ranking]  # type: ignore[attr-defined]
    if not ranking:
        return None
    if isinstance(ranking[0], str):
        return ranking[0], parsed.confidence, [(r, 0.0) for r in ranking[1:]]  # type: ignore[attr-defined]
    return ranking[0].id, ranking[0].score, [(r.id, r.score) for r in ranking[1:]]


def ranked_candidates(
    choice: str, conf: float, ranking: list[tuple[str, float]], valid: list[str]
) -> list[tuple[str, float]]:
    """(choice, conf) then the ranked alternatives: valid, deduplicated, order kept."""
    out = [(choice, conf)]
    seen = {choice, ABSTAIN}
    for cid, c in ranking:
        if cid in valid and cid not in seen:
            seen.add(cid)
            out.append((cid, clamp01(c)))
    return out


def chat_params(chat: Any) -> dict[str, Any]:
    """Sampling/provider params of a chat model that change its output (cache key part)."""
    return {
        k: getattr(chat, k, None)
        for k in ("model_name", "temperature", "seed", "max_tokens", "extra_body")
    }


def rendered(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    return [{"type": m.type, "content": m.content} for m in messages]


def choice_probability(raw: AIMessage | None, choice: str) -> float | None:
    """P(choice) = exp(sum of the logprobs of the tokens spelling the `choice` value) in
    the JSON reply; None when the response carries no logprobs or the value is not found.
    Under a grammar (enum) the first differing token carries the decision."""
    content = ((raw.response_metadata or {}).get("logprobs") or {}).get("content") if raw else None
    if not content:
        return None
    text, spans = "", []
    for tok in content:
        start = len(text)
        text += tok.get("token", "")
        spans.append((start, len(text), float(tok.get("logprob") or 0.0)))
    field = '"choice"' if '"choice"' in text else '"ranking"'  # ranking: first id = choice
    key = text.find(field)
    if key < 0:
        return None
    start = text.find(f'"{choice}"', key + len(field))
    if start < 0:
        return None
    lo, hi = start + 1, start + 1 + len(choice)
    total = sum(lp for a, b, lp in spans if a < hi and b > lo)
    return math.exp(total)


class LLMRouter(BaseRouter):
    name = "llm"  # instance attribute when built for an `llm_<suffix>` strategy
    paid = True

    def __init__(
        self,
        chat: Any,
        settings: Settings,
        *,
        model: str,
        history_turns: int = 4,
        allow_abstain: bool = False,
        cache: ResponseCache | None = None,
        name: str = "llm",
        confidence: Literal["self_reported", "logprob"] = "self_reported",
        prompt_variant: str = "P0",
        calibration: dict[str, Calibration] | None = None,
    ) -> None:
        super().__init__(cache=cache, calibration=calibration)
        self.chat = chat
        self.settings = settings
        self._model = model
        self.history_turns = history_turns
        self.allow_abstain = allow_abstain
        self.name = name
        self.confidence_mode = confidence
        self.prompt_variant = prompt_variant
        self.spec = parse_variant(prompt_variant)

    @property
    def model(self) -> str | None:
        return self._model

    def _request(
        self, inp: RoutingInput, options: list[RouteOption]
    ) -> tuple[list[BaseMessage], type[BaseModel]]:
        ids = [o.id for o in options] + ([ABSTAIN] if self.allow_abstain else [])
        messages = build_messages(
            inp,
            options,
            history_turns=self.history_turns,
            allow_abstain=self.allow_abstain,
            json_reply=self.confidence_mode == "logprob",  # json_mode: the prompt has the shape
            model=self._model,
            spec=self.spec,
        )
        ranked = [o.id for o in options] if inp.level == "tool" else None
        return messages, choice_schema(ids, ranked, self.spec)

    def cache_params(self, inp: RoutingInput, options: list[RouteOption]) -> dict[str, Any]:
        messages, schema = self._request(inp, options)
        return {
            "model": self._model,
            "history_turns": self.history_turns,
            "allow_abstain": self.allow_abstain,
            "confidence": self.confidence_mode,
            "chat": chat_params(self.chat),
            "prompt": rendered(messages),
            "schema": schema.model_json_schema(),
        }

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        messages, schema = self._request(inp, options)
        option_ids = [o.id for o in options]
        # A dict schema (the same strict schema the SDK would send for the model class) keeps
        # malformed replies as `parsing_error` with the raw message (cost); a pydantic class
        # would raise inside the client and lose both. Validation happens below.
        runnable = structured_runnable(
            self.chat,
            {**to_strict_json_schema(schema), "title": schema.__name__},
            json_mode=self.confidence_mode == "logprob",
        )
        stats = RetryStats()
        static_chars, dynamic_chars = prompt_chars(messages)

        def _usage(u: dict[str, Any]) -> dict[str, Any]:
            return {
                **u,
                "calls": 1,
                "attempts": stats.attempts,
                "call_ms": stats.call_ms,
                "queue_ms": stats.queue_ms,
                "retry_ms": stats.retry_ms,
                "static_chars": static_chars,
                "dynamic_chars": dynamic_chars,
            }

        try:
            out: dict[str, Any] = await call_with_retry(
                lambda: runnable.ainvoke(messages),
                model=self._model,
                settings=self.settings,
                stats=stats,
                provider=getattr(self.chat, "provider_name", None),
            )
        except Exception as exc:  # billed reply the client rejected: keep its usage
            billed = dict(getattr(exc, "call_usage", None) or {"cost_usd": 0.0})
            cost = float(billed.pop("cost_usd", 0.0) or 0.0)
            attach_partial_usage(exc, cost, _usage(billed))
            raise
        raw: AIMessage | None = out.get("raw")
        usage = extract_call_usage(raw)
        cost = usage.pop("cost_usd")
        usage = _usage(usage)
        parsed, error = None, out.get("parsing_error")
        if error is None and out.get("parsed") is not None:
            try:
                reply = trim_ranking(out["parsed"], min(self.spec.rank_k, len(options)))
                parsed = schema.model_validate(reply)
            except ValidationError as exc:
                error = exc
        read = read_choice(parsed) if parsed is not None else None
        if read is None:
            usage["parse_fail"] = True
            usage["parsing_error"] = repr(error)[:300]
            return RouteDecision(
                choice=None, confidence=0.0, strategy=self.name, cost_usd=cost, usage=usage
            )
        picked, conf, ranking = read
        choice = None if picked == ABSTAIN else picked
        conf = clamp01(conf)
        if self.confidence_mode == "logprob":
            usage["self_reported_confidence"] = conf
            p = choice_probability(raw, picked)
            if p is None:  # no logprobs returned: keep the choice, trust nothing about it
                usage["confidence_missing"] = True
            conf = clamp01(p) if p is not None else 0.0
        return RouteDecision(
            choice=choice,
            confidence=conf if choice is not None else 0.0,
            candidates=ranked_candidates(picked, conf, ranking, option_ids),
            strategy=self.name,
            cost_usd=cost,
            usage=usage,
        )
