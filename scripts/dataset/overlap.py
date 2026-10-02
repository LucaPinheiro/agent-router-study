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
from typing import Any

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import Case, case_text, normalize  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LEXICAL_THRESHOLD = 0.9
SEMANTIC_THRESHOLD = 0.9
EMBED_MODEL = "qwen3-embedding:8b-q8_0"
PHASE2_EMBED_MODEL = "amazon.titan-embed-text-v2:0"  # phase 2: no local model (Bedrock)
# Titan cosine equivalent to the phase-1 qwen 0.9 (rank-matched on the 849 phase-1 cases;
# data/audit/titan_threshold.json, scripts/dataset/calibrate_titan_threshold.py)
PHASE2_SEMANTIC_THRESHOLD = 0.71
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


_LEAK: Any = None


def leak_rules() -> Any:
    """`tests/test_leakage.py` as a module: its catalog units and lexical rule are the single
    source of truth for catalog leakage (normalized equality, containment of a >= 4-word text,
    `SequenceMatcher` >= 0.90 on >= 3-word units; semantic cosine >= 0.90 on >= 4-word units)."""
    global _LEAK
    if _LEAK is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_test_leakage", ROOT / "tests" / "test_leakage.py"
        )
        assert spec and spec.loader
        _LEAK = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_LEAK)
    return _LEAK


def leak_hit(c: Case) -> str | None:
    """First catalog unit that the repo leakage test would flag on any user turn of `c`."""
    leak = leak_rules()
    units = leak.catalog_units()
    for turn in (t.content for t in c.turns if t.role == "user"):
        msg = leak.norm(turn)
        for unit, origin in units.items():
            if kind := leak.lexical_hit(unit, msg):
                return f"leak_{kind.split()[0]}:{origin}:{unit[:40]}"
    return None


def leak_semantic_units() -> list[str]:
    leak = leak_rules()
    return sorted(u for u in leak.catalog_units() if len(u.split()) >= leak.MIN_SEMANTIC_WORDS)


def catalog_sha256(files: Sequence[Path] = CATALOG_FILES) -> str:
    h = hashlib.sha256()
    for path in files:
        if path.exists():
            h.update(path.relative_to(ROOT).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def user_turns(c: Case) -> list[str]:
    return [normalize(t.content) for t in c.turns if t.role == "user"]


def max_ratio(text: str, refs: Iterable[str], floor: float = 0.0) -> tuple[float, str]:
    """Highest `SequenceMatcher` ratio of `text` against `refs` (upper-bound pruned); refs whose
    ratio cannot reach `floor` are skipped, so a result below `floor` is only a lower bound."""
    best, best_ref = 0.0, ""
    sm = SequenceMatcher(None, autojunk=False)
    sm.set_seq2(text)
    for ref in refs:
        sm.set_seq1(ref)
        bound = max(best, floor)
        if sm.real_quick_ratio() < bound or sm.quick_ratio() < bound:
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
    r, _ = max_ratio(text, case_refs, threshold)
    if r >= threshold:
        return f"lexical_case:{r:.3f}"
    turns = user_turns(c)
    if any(t in set(unit_refs) for t in turns):
        return "exact_catalog"
    for t in turns:
        r, _ = max_ratio(t, unit_refs, threshold)
        if r >= threshold:
            return f"lexical_catalog:{r:.3f}"
    return leak_hit(c)


def semantic_text(c: Case) -> str:
    """Text embedded for the semantic check: the user turns (raw, not normalized)."""
    return " | ".join(t.content for t in c.turns if t.role == "user")


class Embedder:
    """Synchronous wrapper over the project's EmbeddingsClient (ledgered). Phase 1 used the local
    Ollama embedder (cost 0, the default); phase 2 runs no local model and passes
    `backend="bedrock"` with `PHASE2_EMBED_MODEL` (Titan v2, cents)."""

    def __init__(self, model: str = EMBED_MODEL, batch: int = 32, backend: str = "ollama") -> None:
        sys.path.insert(0, str(ROOT / "src"))
        from routing_study.llm import EmbeddingsClient
        from routing_study.settings import Settings

        region = "sa-east-1" if backend == "bedrock" else None
        self._make = lambda http: EmbeddingsClient(
            Settings(), model, backend=backend, http=http, region=region
        )
        self.batch = batch
        self._cache: dict[str, np.ndarray] = {}
        self._disk = (
            Path.home() / ".cache" / "routing_study" / f"embed_{model.replace(':', '_')}.npz"
        )
        try:
            with np.load(self._disk) as z:
                self._disk_cache = {k: z[k] for k in z.files}
        except (OSError, ValueError):
            self._disk_cache = {}

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        for t in dict.fromkeys(texts):
            if t not in self._cache and self._key(t) in self._disk_cache:
                self._cache[t] = self._disk_cache[self._key(t)]
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
            self._disk_cache.update({self._key(t): self._cache[t] for t in todo})
            self._disk.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self._disk, **self._disk_cache)
        return np.stack([self._cache[t] for t in texts]) if texts else np.zeros((0, 1))


def max_cosine(query: np.ndarray, refs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per query row: max cosine against `refs` (unit vectors) and its argmax."""
    if len(refs) == 0 or len(query) == 0:
        return np.zeros(len(query)), np.zeros(len(query), dtype=int)
    sims = query @ refs.T
    return sims.max(axis=1), sims.argmax(axis=1)


def report(out: Path = ROOT / "data" / "audit" / "overlap_report.json") -> dict[str, object]:
    """Leakage/duplicate report for test-v2 (vs the 500 existing cases, the catalog and
    itself) and the committed leakage check of test-v1 and dev vs the catalog."""
    data = ROOT / "data"

    def load(name: str) -> list[Case]:
        path = data / name
        return [Case.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]

    existing = load("seed.jsonl") + load("synthetic.jsonl")
    v2 = load("dataset_test_v2.jsonl")
    units = catalog_units()
    refs = [case_text(c) for c in existing]
    emb = Embedder()
    ev2 = emb([semantic_text(c) for c in v2])
    eex = emb([semantic_text(c) for c in existing])
    eun = emb(units)
    s_case, _ = max_cosine(ev2, eex)
    s_cat, _ = max_cosine(ev2, eun)
    within = ev2 @ ev2.T
    np.fill_diagonal(within, -1)
    s_within = within.max(axis=1)

    def lex(cases: list[Case], against_cases: bool) -> list[float]:
        out_ = []
        for c in cases:
            if against_cases:
                out_.append(max_ratio(case_text(c), refs, 0.8)[0])
            else:
                out_.append(max(max_ratio(t, units, 0.8)[0] for t in user_turns(c)))
        return out_

    def summ(xs: Sequence[float], thr: float) -> dict[str, float | int]:
        a = np.asarray(xs, dtype=float)
        return {"max": round(float(a.max()), 4), f"n_ge_{thr}": int((a >= thr).sum())}

    rep: dict[str, object] = {
        "catalog_units": len(units),
        "catalog_sha256": catalog_sha256(),
        "test_v2": {
            "n": len(v2),
            "lexical_vs_500_cases": summ(lex(v2, True), LEXICAL_THRESHOLD),
            "lexical_vs_catalog": summ(lex(v2, False), LEXICAL_THRESHOLD),
            "semantic_vs_500_cases": summ(s_case, SEMANTIC_THRESHOLD),
            "semantic_vs_catalog": summ(s_cat, SEMANTIC_THRESHOLD),
            "semantic_within_v2_nn": summ(s_within, SEMANTIC_THRESHOLD),
            "id_overlap_with_500": len({c.id for c in v2} & {c.id for c in existing}),
        },
    }
    for name in ("dataset_test.jsonl", "dataset_dev.jsonl"):
        cases = load(name)
        s, _ = max_cosine(emb([semantic_text(c) for c in cases]), eun)
        rep[name] = {
            "n": len(cases),
            "lexical_vs_catalog": summ(lex(cases, False), 0.95),
            "semantic_vs_catalog": summ(s, SEMANTIC_THRESHOLD),
        }
    out.write_text(json.dumps(rep, indent=2) + "\n")
    return rep


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
