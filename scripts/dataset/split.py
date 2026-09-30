"""Stratified 30/70 dev/test split by category (fixed seed) + distribution report."""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import CATEGORIES, TARGET_DIST, Case  # noqa: E402

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


def main() -> None:
    cases = load(DATA / "seed.jsonl") + load(DATA / "synthetic.jsonl")
    rng = random.Random(SEED)
    dev: list[Case] = []
    test: list[Case] = []
    for cat in CATEGORIES:
        group = sorted((c for c in cases if c.category == cat), key=lambda c: c.id)
        rng.shuffle(group)
        k = round(len(group) * DEV_FRAC)
        dev += group[:k]
        test += group[k:]
    for name, part in (("dataset_dev.jsonl", dev), ("dataset_test.jsonl", test)):
        with (DATA / name).open("w") as f:
            for c in sorted(part, key=lambda c: c.id):
                f.write(c.model_dump_json() + "\n")
    print(f"total={len(cases)} dev={len(dev)} test={len(test)}")
    ok = report("ALL", cases) & report("DEV", dev) & report("TEST", test)
    print("\nDISTRIBUTION WITHIN +/-2pp:", "OK" if ok else "FAIL")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
