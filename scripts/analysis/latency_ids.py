"""Case ids of the latency benchmark (methodology-final M8): a stratified (by category, seeded)
sample of N cases, dealt round-robin into B blocks of the same category mix. The manifest runs
every strategy on block 1, then every strategy on block 2, ... so all strategies share one time
window and API drift is spread over them (block-level interleaving).

Reads ONLY `id` and `category` of each case: no message text.

  uv run python scripts/analysis/latency_ids.py [--split test_v2] [--n 100] [--blocks 4]
      [--out-dir config/manifest]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from routing_study.eval.runner import SAMPLE_SEED, stratified_sample


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test_v2")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--blocks", type=int, default=4)
    ap.add_argument("--out-dir", type=Path, default=Path("config/manifest"))
    a = ap.parse_args()
    rows = []
    for line in Path(f"data/dataset_{a.split}.jsonl").read_text("utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            rows.append({"id": case["id"], "category": case["category"]})
    sample = stratified_sample(rows, a.n, SAMPLE_SEED + 1)  # not the --limit sample
    by_cat: dict[str, list[str]] = {}
    for r in sample:
        by_cat.setdefault(r["category"], []).append(r["id"])
    blocks: list[list[str]] = [[] for _ in range(a.blocks)]
    k = 0
    for cat in sorted(by_cat):
        for cid in sorted(by_cat[cat]):
            blocks[k % a.blocks].append(cid)
            k += 1
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for b, ids in enumerate(blocks, 1):
        out = a.out_dir / f"latency_{a.split}_b{b}.ids"
        out.write_text("".join(f"{i}\n" for i in sorted(ids)), "utf-8")
        print(f"{out}: {len(ids)}")


if __name__ == "__main__":
    main()
