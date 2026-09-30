"""Catalog examples must not leak the held-out test set (verbatim or contained, normalized)."""

import json
import re
import unicodedata
from pathlib import Path

from mcp_server.core import RDNS, REGISTRY

TEST_SET = Path(__file__).resolve().parents[2] / "data" / "dataset_test.jsonl"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def test_no_catalog_example_equals_a_test_message() -> None:
    held_out: dict[str, str] = {}
    for line in TEST_SET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            held_out[_norm(case["turns"][-1]["content"])] = case["id"]
    leaks = [
        f"{tool.name}: {example!r} ~ {case_id}"
        for tool in REGISTRY
        for example in tool.meta[f"{RDNS}/examples"]  # type: ignore[index]
        for message, case_id in held_out.items()
        if _overlaps(_norm(example), message)
    ]
    assert not leaks, "\n".join(leaks)


def _overlaps(a: str, b: str, min_words: int = 4) -> bool:
    """Equal, or the shorter text (>= min_words words) appears whole inside the longer one."""
    short, long_ = sorted((a, b), key=len)
    if a == b:
        return True
    return len(short.split()) >= min_words and f" {short} " in f" {long_} "
