"""Routing contract shared by every strategy and both stages (skill, tool)."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

GLOBAL_OPTION = "__global__"
ABSTAIN = "__abstain__"


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RouteOption(BaseModel):
    id: str
    description: str
    examples: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    # Prompt-only catalog data for the LLM/Jev prompt variants (docs/prompt-apex.md). Excluded
    # from dumps, so response-cache keys of every router stay as they were; LLM/Jev routers key
    # on their rendered prompt instead.
    # `avoid`: the catalog's DON'T USE FOR clauses as (situation, ids that handle it) at this
    # level; `shots`: catalog example messages resolved to this option.
    avoid: list[tuple[str, list[str]]] = Field(default_factory=list, exclude=True)
    shots: list[str] = Field(default_factory=list, exclude=True)


class RoutingInput(BaseModel):
    message: str
    history: list[Message] = Field(default_factory=list)
    level: Literal["skill", "tool"]
    loaded_skill: str | None = None


class RouteDecision(BaseModel):
    choice: str | None  # None = abstention
    confidence: float = Field(ge=0.0, le=1.0)
    candidates: list[tuple[str, float]] = Field(default_factory=list)
    strategy: str
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    usage: dict = Field(default_factory=dict)
    cached: bool = False


class Router(Protocol):
    name: str

    async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision: ...
