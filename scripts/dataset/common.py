"""Shared catalog and schema for the routing dataset."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CATEGORIES = ["direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial"]
TARGET_DIST = {
    "direto": 0.30,
    "parafrase": 0.25,
    "ambiguo": 0.20,
    "multiturno": 0.10,
    "fora_escopo": 0.10,
    "adversarial": 0.05,
}

SKILL_TOOLS: dict[str, list[str]] = {
    "__global__": ["get_customer_profile", "search_help_center", "escalate_to_human"],
    "pedidos_logistica": [
        "get_order_status",
        "track_shipment",
        "update_delivery_address",
        "reschedule_delivery",
        "cancel_order",
    ],
    "pagamentos_reembolsos": [
        "get_payment_status",
        "generate_boleto_second_copy",
        "request_refund",
        "get_refund_status",
        "dispute_charge",
    ],
    "trocas_devolucoes": [
        "check_return_eligibility",
        "create_return_request",
        "generate_return_label",
        "create_exchange",
        "open_warranty_claim",
    ],
}
TOOL_SKILL = {t: s for s, ts in SKILL_TOOLS.items() for t in ts}
TOOL_SKILL["__abstain__"] = "__abstain__"
ALL_TOOLS = [t for ts in SKILL_TOOLS.values() for t in ts]

VALID_SKILLS = set(SKILL_TOOLS) | {"__abstain__"}
VALID_TOOLS = set(ALL_TOOLS) | {"__abstain__"}

N_CUSTOMERS = 20
ORDERS_PER_CUSTOMER = 3


def customer_orders(k: int) -> list[str]:
    """Customer C00k owns orders O(3k-2)..O(3k)."""
    return [f"O{3 * k - 3 + i:04d}" for i in (1, 2, 3)]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class Expected(BaseModel):
    acceptable_skills: list[str] = Field(min_length=1)
    acceptable_tools: list[str] = Field(min_length=1)
    args: dict[str, object] = Field(default_factory=dict)

    @field_validator("acceptable_skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        bad = set(v) - VALID_SKILLS
        if bad:
            raise ValueError(f"unknown skills {bad}")
        return v

    @field_validator("acceptable_tools")
    @classmethod
    def _tools(cls, v: list[str]) -> list[str]:
        bad = set(v) - VALID_TOOLS
        if bad:
            raise ValueError(f"unknown tools {bad}")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> Expected:
        derived = {TOOL_SKILL[t] for t in self.acceptable_tools}
        if derived != set(self.acceptable_skills):
            raise ValueError("acceptable_skills inconsistent with acceptable_tools")
        return self


class Case(BaseModel):
    id: str
    category: Literal["direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial"]
    customer_id: str = Field(pattern=r"^C0(0[1-9]|1[0-9]|20)$")
    source: Literal["seed", "synthetic"]
    reviewed: bool = False
    turns: list[Turn] = Field(min_length=1)
    expected: Expected

    @model_validator(mode="after")
    def _turns(self) -> Case:
        if self.turns[-1].role != "user":
            raise ValueError("last turn must be user")
        if self.category == "multiturno" and len(self.turns) < 3:
            raise ValueError("multiturno needs history")
        return self


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def case_text(c: Case) -> str:
    return normalize(" | ".join(t.content for t in c.turns if t.role == "user"))
