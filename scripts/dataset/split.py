"""Stratified 30/70 dev/test split by category (fixed seed) + distribution report.

Label fixes (`label_fix`) live in the source files (seed/synthetic), so a rebuild keeps them;
the split asserts none is lost.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import CATEGORIES, TARGET_DIST, Case, case_dict  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"
SEED = 20260929
DEV_FRAC = 0.30
TOL_PP = 2.0


def load(path: Path) -> list[Case]:
    return [Case.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]


def report(name: str, cases: list[Case]) -> bool:
    n = len(cases)
    cnt = Counter(c.category for c in cases)
    ok = True
    print(f"\n{name} (n={n})")
    print(f"{'category':<13}{'n':>5}{'actual%':>9}{'target%':>9}{'delta_pp':>10}")
    for cat in CATEGORIES:
        actual = 100 * cnt[cat] / n
        target = 100 * TARGET_DIST[cat]
        flag = "" if abs(actual - target) <= TOL_PP else "  OUT"
        ok &= not flag
        print(f"{cat:<13}{cnt[cat]:>5}{actual:>9.1f}{target:>9.1f}{actual - target:>+10.1f}{flag}")
    return ok


def build(cases: list[Case]) -> tuple[list[Case], list[Case]]:
    rng = random.Random(SEED)
    dev: list[Case] = []
    test: list[Case] = []
    for cat in CATEGORIES:
        group = sorted((c for c in cases if c.category == cat), key=lambda c: c.id)
        rng.shuffle(group)
        k = round(len(group) * DEV_FRAC)
        dev += group[:k]
        test += group[k:]
    return sorted(dev, key=lambda c: c.id), sorted(test, key=lambda c: c.id)


def check_label_fixes(cases: list[Case], dev: list[Case], test: list[Case]) -> None:
    """Every corrected source row reaches the split with its marker and fixed labels."""
    out = {c.id: c for c in dev + test}
    for c in cases:
        if c.label_fix is None:
            continue
        got = out.get(c.id)
        assert got is not None and got.label_fix == c.label_fix, f"label_fix lost: {c.id}"
        assert got.expected == c.expected, f"label_fix labels changed: {c.id}"


def main(data: Path = DATA, out: Path = DATA) -> None:
    cases = load(data / "seed.jsonl") + load(data / "synthetic.jsonl")
    dev, test = build(cases)
    check_label_fixes(cases, dev, test)
    for name, part in (("dataset_dev.jsonl", dev), ("dataset_test.jsonl", test)):
        with (out / name).open("w") as f:
            for c in part:
                f.write(json.dumps(case_dict(c), ensure_ascii=False) + "\n")
    print(
        f"total={len(cases)} dev={len(dev)} test={len(test)} "
        f"label_fix={sum(c.label_fix is not None for c in cases)}"
    )
    ok = report("ALL", cases) & report("DEV", dev) & report("TEST", test)
    print("\nDISTRIBUTION WITHIN +/-2pp:", "OK" if ok else "FAIL")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
