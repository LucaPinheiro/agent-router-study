"""Catalog leakage (F10): no router-visible catalog text may reproduce a dataset message.

Units: every text a router can see — tool descriptions (WHEN TO USE quotes, each
sentence and `;` clause), `_meta` examples and keywords, SKILL.md (frontmatter examples and
body), server instructions, host prompt fragments. Tool titles are left out: no router or
executor prompt carries them (`Catalog.openai_tool` sends description + inputSchema only).
Tool/skill identifiers and `(use tool)` pointers are stripped: a message quoting a tool name
(adversarial cases) is not leakage. References: the last user turn and every user turn of
every `data/dataset_*.jsonl` split (dev, test, test-v2 when present).

- Lexical (unit): normalized equality, whole containment of a >= 4-word text, or
  `SequenceMatcher` ratio >= 0.90 (units of >= 3 words).
- Semantic (integration, local Ollama `qwen3-embedding:8b-q8_0` through the project's
  `EmbeddingsClient`): cosine >= 0.90 between a unit of >= 4 words and a user turn.
"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp_server" / "src" / "mcp_server"
DATASETS = sorted((ROOT / "data").glob("dataset_*.jsonl"))
CATALOG_FILES = [
    *sorted((SERVER / "skills").glob("*/SKILL.md")),
    SERVER / "instructions.md",
    *sorted((ROOT / "src" / "routing_study" / "prompts").glob("*.md")),
]
TOOLS_LIST = ROOT / "mcp_server" / "tools_list.json"
LEXICAL_THRESHOLD = 0.90
SEMANTIC_THRESHOLD = 0.90
MIN_FUZZY_WORDS = 3  # ratio on shorter units only flags generic phrases
# cosine: a 3-word intent label ("abrir a devolução") is always near a short same-intent
# message; paraphrase leakage needs a unit long enough to carry wording
MIN_SEMANTIC_WORDS = 4
MIN_CONTAINED_WORDS = 4
EMBED_MODEL = "qwen3-embedding:8b-q8_0"
_IDENTIFIER = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
_USE = re.compile(r"\(use [^)]*\)")  # DON'T USE FOR pointers: identifiers only


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _segments(text: str) -> list[str]:
    """Quoted snippets, lines, sentences and `;` clauses of a free text."""
    out: list[str] = re.findall(r"[\"“]([^\"”]{4,})[\"”]", text)
    for line in text.splitlines():
        line = re.sub(r"^[\s#>*|-]+", "", line).strip()
        out.append(line)
        out.extend(re.split(r"(?<=[.!?;:])\s+|\s*\|\s*", line))
    return [s for s in out if s.strip()]


def catalog_units() -> dict[str, str]:
    """{normalized unit: where it comes from} for every router-visible catalog text."""
    units: dict[str, str] = {}

    def add(texts: list[str], origin: str) -> None:
        for t in texts:
            # tool/skill identifiers are the protocol, not wording: a message quoting one
            # (adversarial cases) is not leakage
            n = norm(_IDENTIFIER.sub(" ", _USE.sub(" ", t)))
            if n:
                units.setdefault(n, origin)

    for tool in json.loads(TOOLS_LIST.read_text(encoding="utf-8"))["tools"]:
        name = tool["name"]
        add(_segments(tool.get("description") or ""), f"{name}.description")
        for key, val in (tool.get("_meta") or {}).items():
            if key.endswith(("/examples", "/keywords")):
                add(list(val), f"{name}.{key.rsplit('/', 1)[1]}")
    for path in CATALOG_FILES:
        add(_segments(path.read_text(encoding="utf-8")), str(path.relative_to(ROOT)))
    return units


def user_turns() -> list[tuple[str, bool, str]]:
    """(case id, is the last user turn, normalized text) over every dataset split."""
    out: list[tuple[str, bool, str]] = []
    for path in DATASETS:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            turns = [t["content"] for t in case["turns"] if t["role"] == "user"]
            for i, text in enumerate(turns):
                out.append((f"{path.stem}:{case['id']}", i == len(turns) - 1, norm(text)))
    return out


def lexical_hit(unit: str, message: str) -> str | None:
    if unit == message:
        return "exact"
    short, long_ = sorted((unit, message), key=len)
    if len(short.split()) >= MIN_CONTAINED_WORDS and f" {short} " in f" {long_} ":
        return "contained"
    if min(len(unit.split()), len(message.split())) >= MIN_FUZZY_WORDS:
        sm = SequenceMatcher(None, unit, message, autojunk=False)
        if sm.real_quick_ratio() >= LEXICAL_THRESHOLD and sm.quick_ratio() >= LEXICAL_THRESHOLD:
            r = sm.ratio()
            if r >= LEXICAL_THRESHOLD:
                return f"ratio {r:.2f}"
    return None


def _report(leaks: list[tuple[str, bool, str, str, str]]) -> str:
    last = {case for case, is_last, *_ in leaks if is_last}
    cases = {case for case, *_ in leaks}
    lines = [f"{len(cases)} cases leak ({len(last)} on the last user turn):"]
    lines += [
        f"  {case}{' [last]' if is_last else ''}: {origin} {unit!r} ~ {kind}"
        for case, is_last, origin, unit, kind in sorted(leaks)
    ]
    return "\n".join(lines)


def test_datasets_are_found() -> None:
    assert {p.stem for p in DATASETS} >= {"dataset_dev", "dataset_test"}


def test_no_catalog_text_lexically_matches_a_user_turn() -> None:
    units = catalog_units()
    leaks = [
        (case, is_last, origin, unit, kind)
        for case, is_last, message in user_turns()
        for unit, origin in units.items()
        if (kind := lexical_hit(unit, message))
    ]
    assert not leaks, _report(leaks)


@pytest.mark.integration
async def test_no_catalog_text_semantically_matches_a_user_turn() -> None:
    """Needs the local Ollama embedder (cost 0)."""
    import httpx
    import numpy as np

    from routing_study.llm import EmbeddingsClient
    from routing_study.settings import Settings

    units = {u: o for u, o in catalog_units().items() if len(u.split()) >= MIN_SEMANTIC_WORDS}
    turns = user_turns()
    texts = sorted(units)
    messages = sorted({m for *_, m in turns})

    async with httpx.AsyncClient(timeout=300) as http:
        client = EmbeddingsClient(Settings(), EMBED_MODEL, backend="ollama", http=http)

        async def embed(batch: list[str]) -> np.ndarray:
            vecs = [
                (await client.embed(batch[i : i + 32])).vectors for i in range(0, len(batch), 32)
            ]
            m = np.concatenate(vecs).astype(np.float32)
            return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)

        u_vecs, m_vecs = await embed(texts), await embed(messages)
    sims = m_vecs @ u_vecs.T
    best = {m: (float(sims[i].max()), texts[int(sims[i].argmax())]) for i, m in enumerate(messages)}
    leaks = [
        (case, is_last, units[best[m][1]], best[m][1], f"cos {best[m][0]:.3f}")
        for case, is_last, m in turns
        if best[m][0] >= SEMANTIC_THRESHOLD
    ]
    assert not leaks, _report(leaks)
