"""Large-catalog (phase 2, `CATALOG_PROFILE=large`) twin of `common.py`: the same case schema,
validated against the 62 tools / 10 skills of `mcp_server/tools_list_large.json`. `common.py`
stays the phase-1 (18-tool) schema, unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from common import CATEGORIES, Turn, case_dict, case_text, normalize  # noqa: F401
from common import SKILL_TOOLS as SKILL_TOOLS_SMALL
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
TOOLS_LIST_L = ROOT / "mcp_server" / "tools_list_large.json"
SKILL_ORDER = [
    "__global__",
    "pedidos_logistica",
    "pagamentos_reembolsos",
    "trocas_devolucoes",
    "assistencia_tecnica",
    "marketplace_vendedores",
    "assinaturas",
    "notas_fiscais_cadastro",
    "promocoes_precos",
    "fidelidade_cashback",
    "cartao_loja_crediario",
]


def _skill_of(tool: dict) -> str:
    meta = tool.get("_meta") or {}
    skill = next(v for k, v in meta.items() if k.endswith("skill"))
    return "__global__" if skill == "global" else skill


_TOOLS = json.loads(TOOLS_LIST_L.read_text(encoding="utf-8"))["tools"]
TOOL_PARAMS_L: dict[str, list[str]] = {
    t["name"]: list((t.get("inputSchema") or {}).get("properties") or {}) for t in _TOOLS
}
SKILL_TOOLS_L: dict[str, list[str]] = {
    s: sorted(t["name"] for t in _TOOLS if _skill_of(t) == s) for s in SKILL_ORDER
}
# the 18 phase-1 tools keep their phase-1 order (the "orig subset" of the catalog-size analysis)
ORIG_TOOLS = [t for ts in SKILL_TOOLS_SMALL.values() for t in ts]
for _s, _ts in SKILL_TOOLS_SMALL.items():
    SKILL_TOOLS_L[_s] = [*_ts, *sorted(set(SKILL_TOOLS_L[_s]) - set(_ts))]
TOOL_SKILL_L = {t: s for s, ts in SKILL_TOOLS_L.items() for t in ts}
TOOL_SKILL_L["__abstain__"] = "__abstain__"
ALL_TOOLS_L = [t for ts in SKILL_TOOLS_L.values() for t in ts]
NEW_TOOLS = [t for t in ALL_TOOLS_L if t not in ORIG_TOOLS]
VALID_SKILLS_L = set(SKILL_TOOLS_L) | {"__abstain__"}
VALID_TOOLS_L = set(ALL_TOOLS_L) | {"__abstain__"}
assert len(ALL_TOOLS_L) == 62 and len(SKILL_TOOLS_L) == 11, (len(ALL_TOOLS_L), SKILL_TOOLS_L)
assert set(ORIG_TOOLS) <= set(ALL_TOOLS_L)


class ExpectedL(BaseModel):
    acceptable_skills: list[str] = Field(min_length=1)
    acceptable_tools: list[str] = Field(min_length=1)
    args: dict[str, object] = Field(default_factory=dict)

    @field_validator("acceptable_skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        bad = set(v) - VALID_SKILLS_L
        if bad:
            raise ValueError(f"unknown skills {bad}")
        return v

    @field_validator("acceptable_tools")
    @classmethod
    def _tools(cls, v: list[str]) -> list[str]:
        bad = set(v) - VALID_TOOLS_L
        if bad:
            raise ValueError(f"unknown tools {bad}")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> ExpectedL:
        derived = {TOOL_SKILL_L[t] for t in self.acceptable_tools}
        if derived != set(self.acceptable_skills):
            raise ValueError("acceptable_skills inconsistent with acceptable_tools")
        return self


class CaseL(BaseModel):
    id: str
    category: Literal["direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial"]
    customer_id: str = Field(pattern=r"^C0(0[1-9]|1[0-9]|20)$")
    source: Literal["synthetic_l"]
    reviewed: bool = False
    turns: list[Turn] = Field(min_length=1)
    expected: ExpectedL
    label_fix: str | None = None
    label_audit: dict[str, object] | None = None

    @model_validator(mode="after")
    def _turns(self) -> CaseL:
        if self.turns[-1].role != "user":
            raise ValueError("last turn must be user")
        if self.category == "multiturno" and len(self.turns) < 3:
            raise ValueError("multiturno needs history")
        return self
