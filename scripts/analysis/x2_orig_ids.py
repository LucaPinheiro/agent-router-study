"""Case ids of the X2 paired catalog-size subset (prereg-v2 §3 X2): every test-L case whose
acceptable tools all lie in the 18 phase-1 tools, or that is out of scope. Same rule as
`orig_case` in scripts/analysis/phase2_b.py (frozen analysis code).

Reads ONLY `id`, `category` and `expected.acceptable_tools` of each case: no message text.

  uv run python scripts/analysis/x2_orig_ids.py [--split test_l]
      [--out config/manifest/x2_test_l_orig.ids]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset"))

from common_l import ORIG_TOOLS  # noqa: E402

MIN_N = 60  # quota guarantee of the test-L generator (plan §2, T4.3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test_l")
    ap.add_argument("--out", type=Path, default=Path("config/manifest/x2_test_l_orig.ids"))
    a = ap.parse_args()
    orig = set(ORIG_TOOLS) | {"__abstain__"}
    ids = []
    for line in Path(f"data/dataset_{a.split}.jsonl").read_text("utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            tools = case["expected"]["acceptable_tools"]
            if case["category"] == "fora_escopo" or all(t in orig for t in tools):
                ids.append(case["id"])
    if len(ids) < MIN_N:
        raise SystemExit(f"orig subset has {len(ids)} cases < {MIN_N}: top up before the freeze")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(f"{i}\n" for i in sorted(ids)), "utf-8")
    print(f"{a.out}: {len(ids)}")


if __name__ == "__main__":
    main()
