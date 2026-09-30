"""Graph state (checkpointed, minimal) and per-run context (live objects, never checkpointed)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from routing_study.catalog import Catalog, ToolOutcome
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import Settings

Outcome = Literal["answered", "abstained", "loop_limit"]


class CaseContext(TypedDict):
    case_id: str
    customer_id: str
    split: str
    repetition: int
    turns: list[dict[str, str]]  # gold history + current user message (last)


class TurnState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    case: CaseContext
    customer: dict[str, Any] | None  # get_customer_profile structuredContent
    skill_decision: dict[str, Any] | None  # PipelineResult dump
    tool_decision: dict[str, Any] | None
    loaded_skill: str | None
    exposed_tools: list[str]
    outcome: Outcome | None


class CatalogSource(Protocol):
    async def get(self) -> tuple[Catalog, str]: ...


class ToolCaller(Protocol):
    async def call(self, name: str, args: dict[str, Any]) -> ToolOutcome: ...


@dataclass
class RunContext:
    settings: Settings
    catalog: CatalogSource
    tools: ToolCaller
    chat: BaseChatModel | None = None  # executor; None in routing-only runs
    skill_pipeline: RoutingPipeline | None = None  # None = native (E0)
    tool_pipeline: RoutingPipeline | None = None
    callbacks: list[BaseCallbackHandler] = field(default_factory=list)
    prompt_versions: dict[str, int] = field(default_factory=dict)  # Langfuse prompt name -> v

    @property
    def native(self) -> bool:
        return self.skill_pipeline is None
