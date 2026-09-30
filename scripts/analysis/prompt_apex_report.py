"""Markdown tables of the router prompt study from tune_router.py `--out` JSON files.

Usage:
  uv run python scripts/analysis/prompt_apex_report.py results/prompt_apex/e5_*.json ...
  uv run python scripts/analysis/prompt_apex_report.py --merge "Sonnet 5" a.json b.json

One row per (file, grid point): CV joint mean ± std, skill/tool accuracy, raw ECE per level,
prompt tokens (static / dynamic estimate), cache read / write, output tokens, cost per 1k
cases, case p50 / p95 and tool-stage p50. When a point appears in several files (subset and
full dev), each row is labelled with its n.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def rows(path: Path) -> list[tuple[str, dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(p["label"].split("=", 1)[-1], p["metrics"]) for p in data["points"]]


def table(items: list[tuple[str, dict[str, Any]]]) -> str:
    head = (
        "| variant | n | joint (CV) | skill | tool | ECE s/t | prompt (static/dyn) | cache r/w "
        "| out | $/1k | p50 / p95 ms | tool p50 |"
    )
    out = [head, "|" + "---|" * 12]
    for name, m in sorted(items, key=lambda kv: -kv[1]["joint_correct_mean"]):
        out.append(
            f"| {name} | {m['n']} | {100 * m['joint_correct_mean']:.1f} ± "
            f"{100 * m['joint_correct_std']:.1f} | {100 * m['skill_correct_all']:.1f} | "
            f"{100 * m['tool_correct_all']:.1f} | {m['ece_skill']:.3f} / {m['ece_tool']:.3f} | "
            f"{m['prompt_tokens']:.0f} ({m['static_tokens']:.0f}/{m['dynamic_tokens']:.0f}) | "
            f"{m['cache_read_tokens']:.0f} / {m['cache_write_tokens']:.0f} | "
            f"{m['completion_tokens']:.0f} | {m['cost_per_1k']:.2f} | "
            f"{m['p50_ms']:.0f} / {m['p95_ms']:.0f} | {m['tool_p50_ms']:.0f} |"
        )
    return "\n".join(out)


def main() -> None:
    if sys.argv[1:2] == ["--merge"]:  # one table over several files (e.g. two full-dev runs)
        title, paths = sys.argv[2], sys.argv[3:]
        print(f"\n### {title}\n")
        print(table([r for p in paths for r in rows(Path(p))]))
        return
    for arg in sys.argv[1:]:
        path = Path(arg)
        print(f"\n### {path.stem}\n")
        print(table(rows(path)))


if __name__ == "__main__":
    main()
