"""Duplicate / leakage checks for new dataset cases.

- Lexical: exact normalized match, or `SequenceMatcher` ratio >= threshold, against the existing
  cases (all user turns joined, `case_text`) and against every router-visible catalog text unit
  (tool titles/descriptions/`_meta` examples, SKILL.md, server instructions, router prompt
  fragments), compared per user turn.
- Semantic: cosine >= threshold with the local embedder (`qwen3-embedding:8b-q8_0` on Ollama,
  through the project's `EmbeddingsClient`), same reference sets.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import Case, case_text, normalize  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LEXICAL_THRESHOLD = 0.9
SEMANTIC_THRESHOLD = 0.9
EMBED_MODEL = "qwen3-embedding:8b-q8_0"
MIN_UNIT_WORDS = 3

CATALOG_FILES = [
    ROOT / "mcp_server" / "tools_list.json",
    *sorted((ROOT / "mcp_server" / "src" / "mcp_server" / "skills").glob("*/SKILL.md")),
    ROOT / "mcp_server" / "src" / "mcp_server" / "instructions.md",
    *sorted((ROOT / "src" / "routing_study" / "prompts").glob("*.md")),
    *sorted((ROOT / "src" / "routing_study" / "prompts" / "routers").glob("*.yaml")),
]


def _segments(text: str) -> list[str]:
    """Lines, sentences and quoted snippets of a free text."""
    out: list[str] = re.findall(r"[\"“']([^\"”']{8,})[\"”']", text)
    for line in text.splitlines():
        line = re.sub(r"^[\s#>*|-]+", "", line).strip()
        out.append(line)
        out.extend(re.split(r"(?<=[.!?;])\s+|\s*\|\s*", line))
    return out


def catalog_units(files: Sequence[Path] = CATALOG_FILES) -> list[str]:
    """Normalized, de-duplicated text units a router can see (>= MIN_UNIT_WORDS words)."""
    raw: list[str] = []
    for path in files:
        if not path.exists():
            continue
        if path.suffix == ".json":
            for tool in json.loads(path.read_text(encoding="utf-8"))["tools"]:
                raw.append(tool.get("title") or "")
                raw.extend(_segments(tool.get("description") or ""))
                meta = tool.get("_meta") or {}
                for key, val in meta.items():
                    if key.endswith("/examples"):
                        raw.extend(val)
        else:
            raw.extend(_segments(path.read_text(encoding="utf-8")))
    units = {normalize(u) for u in raw}
    return sorted(u for u in units if len(u.split()) >= MIN_UNIT_WORDS)


def catalog_sha256(files: Sequence[Path] = CATALOG_FILES) -> str:
    h = hashlib.sha256()
    for path in files:
        if path.exists():
            h.update(path.relative_to(ROOT).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def user_turns(c: Case) -> list[str]:
    return [normalize(t.content) for t in c.turns if t.role == "user"]


def max_ratio(text: str, refs: Iterable[str]) -> tuple[float, str]:
    """Highest `SequenceMatcher` ratio of `text` against `refs` (upper-bound pruned)."""
    best, best_ref = 0.0, ""
    sm = SequenceMatcher(None, autojunk=False)
    sm.set_seq2(text)
    for ref in refs:
        sm.set_seq1(ref)
        if sm.real_quick_ratio() <= best or sm.quick_ratio() <= best:
            continue
        r = sm.ratio()
        if r > best:
            best, best_ref = r, ref
    return best, best_ref


def lexical_hit(
    c: Case,
    case_refs: Sequence[str],
    unit_refs: Sequence[str],
    threshold: float = LEXICAL_THRESHOLD,
) -> str | None:
    """Reason string when `c` duplicates a reference case or a catalog unit, else None."""
    text = case_text(c)
    if text in set(case_refs):
        return "exact_case"
    r, _ = max_ratio(text, case_refs)
    if r >= threshold:
        return f"lexical_case:{r:.3f}"
    turns = user_turns(c)
    if any(t in set(unit_refs) for t in turns):
        return "exact_catalog"
    for t in turns:
        r, _ = max_ratio(t, unit_refs)
        if r >= threshold:
            return f"lexical_catalog:{r:.3f}"
    return None


def semantic_text(c: Case) -> str:
    """Text embedded for the semantic check: the user turns (raw, not normalized)."""
    return " | ".join(t.content for t in c.turns if t.role == "user")


class Embedder:
    """Synchronous wrapper over the project's EmbeddingsClient (Ollama, cost 0, ledgered)."""

    def __init__(self, model: str = EMBED_MODEL, batch: int = 32) -> None:
        sys.path.insert(0, str(ROOT / "src"))
        from routing_study.llm import EmbeddingsClient
        from routing_study.settings import Settings

        self._make = lambda http: EmbeddingsClient(Settings(), model, backend="ollama", http=http)
        self.batch = batch
        self._cache: dict[str, np.ndarray] = {}

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        todo = [t for t in dict.fromkeys(texts) if t not in self._cache]

        async def run() -> None:  # a fresh HTTP client per event loop
            async with httpx.AsyncClient(timeout=300) as http:
                client = self._make(http)
                for i in range(0, len(todo), self.batch):
                    chunk = todo[i : i + self.batch]
                    res = await client.embed(chunk)
                    vecs = np.asarray(res.vectors, dtype=np.float32)
                    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
                    self._cache.update(zip(chunk, vecs, strict=True))

        if todo:
            asyncio.run(run())
        return np.stack([self._cache[t] for t in texts]) if texts else np.zeros((0, 1))


def max_cosine(query: np.ndarray, refs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per query row: max cosine against `refs` (unit vectors) and its argmax."""
    if len(refs) == 0:
        return np.zeros(len(query)), np.zeros(len(query), dtype=int)
    sims = query @ refs.T
    return sims.max(axis=1), sims.argmax(axis=1)
