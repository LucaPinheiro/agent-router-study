"""Case ids of the paid RQ5 runs (docs/rq5-design.md): every test-v2 case with a held-out tool
among its acceptable tools, plus a stratified (by category, seeded) regression sample of the
other cases.

Reads ONLY `id`, `category` and `expected.acceptable_tools` of each case: no message text.

  uv run python scripts/analysis/rq5_ids.py [--split test_v2] [--sample 60]
      [--out config/manifest/rq5_test_v2.ids]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from routing_study.eval.rq5 import held_out_tools
from routing_study.eval.runner import SAMPLE_SEED, stratified_sample


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test_v2")
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--out", type=Path, default=Path("config/manifest/rq5_test_v2.ids"))
    a = ap.parse_args()
    held = set(held_out_tools())
    rows = []
    for line in Path(f"data/dataset_{a.split}.jsonl").read_text("utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            rows.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "tools": set(case["expected"]["acceptable_tools"]),
                }
            )
    affected = [r for r in rows if r["tools"] & held]
    others = [r for r in rows if not r["tools"] & held]
    sample = stratified_sample(others, a.sample, SAMPLE_SEED)
    ids = sorted({r["id"] for r in affected} | {r["id"] for r in sample})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(f"{i}\n" for i in ids), "utf-8")
    print(f"{a.out}: {len(affected)} affected + {len(sample)} regression sample = {len(ids)}")


if __name__ == "__main__":
    main()
