"""Layered system prompt (plan §4.4), static -> dynamic so the prefix stays cacheable.

[1] <host_rules>  [2] <server_instructions>  [3] <available_skills> (native only)   <- cache
[4] <skill> SKILL.md of the loaded skill                                           <- cache
[5] <customer_context>  customer id, first name, order ids only: order state must come from
                        tool calls (the full profile stays in the result record for grounding)
`cache_control` breakpoints go through OpenRouter to Anthropic (verified: cache_write_tokens
on the first call, cached_tokens on the next).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routing_study.catalog import Catalog

_DIR = Path(__file__).parent
HOST_RULES = (_DIR / "host_rules.md").read_text(encoding="utf-8").strip()
AVAILABLE_SKILLS = (_DIR / "available_skills.md").read_text(encoding="utf-8").strip()
PROMPT_HASH = hashlib.sha256((HOST_RULES + "\0" + AVAILABLE_SKILLS).encode()).hexdigest()[:12]
_CACHE = {"type": "ephemeral"}


def _block(text: str, *, cache: bool) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = _CACHE
    return block


def escape_data(text: str) -> str:
    """Neutralize tag delimiters inside reference data so it cannot close its block (text
    without `<` / `>` is returned unchanged)."""
    return text.replace("<", "\\u003c").replace(">", "\\u003e")


def tool_result(text: str, structured: dict[str, Any] | None) -> str:
    """ToolMessage content for the executor: the MCP text plus a compact JSON of its
    structuredContent (code, recoverable, details.options, items...), delimited and escaped."""
    text = escape_data(text)  # MCP text is data too: it must not open/close host blocks
    if not structured:
        return text
    data = escape_data(json.dumps(structured, ensure_ascii=False, separators=(",", ":")))
    return f"{text}\n<structured_content>\n{data}\n</structured_content>"


def system_blocks(
    catalog: Catalog, *, native: bool, skill: str | None, customer: dict[str, Any] | None
) -> list[dict[str, Any]]:
    static = [
        f"<host_rules>\n{HOST_RULES}\n</host_rules>",
        f"<server_instructions>\n{escape_data(catalog.instructions.strip())}\n</server_instructions>",
    ]
    if native:
        listing = "\n".join(
            f"- {s.id}: {escape_data(s.description)}" for s in catalog.skills.values()
        )
        static.append(
            "<available_skills>\n"
            + AVAILABLE_SKILLS.replace("{skills}", listing)
            + "\n</available_skills>"
        )
    blocks = [_block("\n\n".join(static), cache=True)]
    if skill and skill in catalog.skills:
        playbook = escape_data(catalog.skills[skill].markdown.strip())
        blocks.append(_block(f'<skill name="{skill}">\n{playbook}\n</skill>', cache=True))
    c = customer or {}
    ctx = json.dumps(
        {
            "customer_id": c.get("customer_id"),
            "first_name": (c.get("name") or "").split(" ")[0] or None,
            "order_ids": [o.get("order_id") for o in c.get("orders") or []],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    blocks.append(
        _block(f"<customer_context>\n{escape_data(ctx)}\n</customer_context>", cache=False)
    )
    return blocks
