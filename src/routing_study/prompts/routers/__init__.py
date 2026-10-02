"""Router prompt variants (LLM and Jev routers), static -> dynamic.

A variant is a config value: `prompt_variant: "P0+P1+P6c"` = `+`-joined tokens from
`variants.yaml`, applied left to right to `PromptSpec()`. The text lives in `en.yaml` /
`pt.yaml`; `TEMPLATE_HASH` covers the three files. See docs/prompt-apex.md.

System message (the cacheable static prefix): rules, `<options>`, then `<guide>` (P1) and
`<examples>` (P2). User message: `<loaded_skill>`, `<history>`, `<message>`.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DIR = Path(__file__).parent
_FILES = ("variants.yaml", "en.yaml", "pt.yaml")
TEMPLATE_HASH = hashlib.sha256(b"\0".join((_DIR / f).read_bytes() for f in _FILES)).hexdigest()[:12]

Output = Literal["verbose", "compact", "scored"]


class PromptSpec(BaseModel):
    """What a variant turns on. `output` shapes the TOOL stage only (the skill stage always
    answers `{choice, confidence}`): verbose = choice + confidence + every other option
    with its confidence (P0); compact = top-`rank_k` ids + one confidence; scored = top-
    `rank_k` [{id, score}]."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: Literal["en", "pt"] = "en"
    guide: bool = False
    shots: int = Field(default=0, ge=0)
    scope: bool = False
    rationale: bool = False
    output: Output = "verbose"
    rank_k: int = Field(default=3, ge=1)


@cache
def variant_tokens() -> dict[str, dict[str, Any]]:
    return yaml.safe_load((_DIR / "variants.yaml").read_text(encoding="utf-8"))


@cache
def templates(language: str) -> dict[str, Any]:
    return yaml.safe_load((_DIR / f"{language}.yaml").read_text(encoding="utf-8"))


@cache
def parse_variant(name: str) -> PromptSpec:
    """`"P0+P1+P6c"` -> PromptSpec; unknown tokens raise ValueError."""
    tokens = variant_tokens()
    data: dict[str, Any] = {}
    for tok in (t.strip() for t in name.split("+")):
        if tok not in tokens:
            raise ValueError(f"unknown prompt variant token {tok!r} (known: {sorted(tokens)})")
        data.update(tokens[tok] or {})
    return PromptSpec.model_validate(data)
