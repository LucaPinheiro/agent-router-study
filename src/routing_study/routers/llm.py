"""LLM router: structured output with an `enum` of option ids + self-reported confidence."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field, create_model

from routing_study.llm import RetryStats, call_with_retry, extract_call_usage
from routing_study.routers.base import ABSTAIN, RouteDecision, RouteOption, RoutingInput
from routing_study.routers.common import BaseRouter, ResponseCache, clamp01, history_text
from routing_study.settings import Settings

_LEVEL_NOUN = {"skill": "skill (domain)", "tool": "tool (action)"}


def build_messages(
    inp: RoutingInput,
    options: list[RouteOption],
    *,
    history_turns: int,
    allow_abstain: bool,
    json_reply: bool,
    model: str = "",
) -> list[BaseMessage]:
    """Routing prompt shared by the LLM and Jev routers, static -> dynamic: rules, options
    (a cache breakpoint on Anthropic models), then loaded skill + history + message."""
    lines = []
    for o in options:
        ex = "; ".join(o.examples[:5])
        lines.append(f"- id: {o.id}\n  description: {o.description}"
                     + (f"\n  examples: {ex}" if ex else ""))
    noun = _LEVEL_NOUN[inp.level]
    rules = [
        f"You route a customer-service message (Brazilian Portuguese) to exactly one {noun}.",
        "Choose the option whose description best matches what the user wants NOW.",
        "Confidence is your probability (0 to 1) that the choice is correct.",
    ]
    if allow_abstain:
        rules.append(f"If no option fits, answer `{ABSTAIN}`.")
    if json_reply:
        ids = ", ".join(f'"{o.id}"' for o in options)
        rules.append(
            'Reply with ONLY a JSON object, no prose, no code fences: '
            '{"choice": <one of [' + ids + (f', "{ABSTAIN}"' if allow_abstain else "")
            + ']>, "confidence": <number 0..1>}'
        )
    system = "\n".join(rules) + "\n\n<options>\n" + "\n".join(lines) + "\n</options>"
    user = f"<message>\n{inp.message}\n</message>"
    hist = history_text(inp, history_turns)
    if hist:
        user = f"<history>\n{hist}\n</history>\n{user}"
    if inp.loaded_skill:
        user = f"<loaded_skill>{inp.loaded_skill}</loaded_skill>\n{user}"
    if model.startswith("anthropic/"):
        block = {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        return [SystemMessage([block]), HumanMessage(user)]
    return [SystemMessage(system), HumanMessage(user)]


def choice_schema(option_ids: list[str]) -> type[BaseModel]:
    return create_model(
        "RouteChoice",
        choice=(Literal[tuple(option_ids)], Field(description="Chosen option id")),  # type: ignore[valid-type]
        confidence=(float, Field(description="Probability (0..1) that the choice is correct")),
    )


class LLMRouter(BaseRouter):
    name: ClassVar[str] = "llm"
    paid: ClassVar[bool] = True

    def __init__(
        self,
        chat: Any,
        settings: Settings,
        *,
        model: str,
        history_turns: int = 4,
        allow_abstain: bool = False,
        cache: ResponseCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.chat = chat
        self.settings = settings
        self._model = model
        self.history_turns = history_turns
        self.allow_abstain = allow_abstain

    @property
    def model(self) -> str | None:
        return self._model

    def _structured(self, ids: list[str]) -> Runnable:
        return self.chat.with_structured_output(
            choice_schema(ids), method="json_schema", include_raw=True, strict=True
        )

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        ids = [o.id for o in options] + ([ABSTAIN] if self.allow_abstain else [])
        messages = build_messages(inp, options, history_turns=self.history_turns,
                                  allow_abstain=self.allow_abstain, json_reply=False,
                                  model=self._model)
        runnable = self._structured(ids)
        stats = RetryStats()
        out: dict[str, Any] = await call_with_retry(
            lambda: runnable.ainvoke(messages), model=self._model, settings=self.settings,
            stats=stats,
        )
        raw: AIMessage | None = out.get("raw")
        usage = extract_call_usage(raw)
        cost = usage.pop("cost_usd")
        usage.update(calls=1, attempts=stats.attempts)
        parsed = out.get("parsed")
        if parsed is None:
            usage["parse_fail"] = True
            usage["parsing_error"] = repr(out.get("parsing_error"))[:300]
            return RouteDecision(choice=None, confidence=0.0, strategy=self.name,
                                 cost_usd=cost, usage=usage)
        choice = None if parsed.choice == ABSTAIN else parsed.choice
        conf = clamp01(parsed.confidence)
        return RouteDecision(
            choice=choice,
            confidence=conf if choice is not None else 0.0,
            candidates=[(parsed.choice, conf)],
            strategy=self.name,
            cost_usd=cost,
            usage=usage,
        )
