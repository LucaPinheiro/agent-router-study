"""Write the dev-L tuned strategy blocks into config/experiments_l/*.yaml (phase 2, T5).

Usage:
  uv run python scripts/analysis/apply_tuned_l.py \\
      docs/results/phase2-dev-l/tuned_blocks.yaml [--check]

The blocks file has two keys:
- `strategies`: {name: block}, replacing `strategies.<name>` in EVERY large config that has it
  (each config carries every shared block, as in phase 1, so a cascade step and its standalone
  router are the same router);
- `per_config`: {config stem: {strategies: {...}, routing: {...}}}, deep-merged afterwards
  (the `llm` block differs per config: Haiku, Ministral, Nemotron, Sonnet; cascade thresholds).
  A `calibration` value replaces the old map as a whole (a level left out is dropped);
- `jev_calibration` (optional): the `strategies.jev.calibration` of every config with a jev
  block (its prompt_track differs per config, so the block itself is not replaced).

The header comment of each config is kept; the YAML body is re-dumped (no inline comments in
these configs). `--check` only reports which files would change. Phase-1 configs are never read.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml

from routing_study.settings import load_settings

CONFIG_DIR = Path("config/experiments_l")


def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if k != "calibration" and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def render(header: list[str], data: dict[str, Any]) -> str:
    body = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=None, width=110, allow_unicode=True
    )
    return "".join(header) + body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("blocks", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    spec = yaml.safe_load(args.blocks.read_text(encoding="utf-8"))
    shared: dict[str, Any] = spec.get("strategies") or {}
    per_config: dict[str, Any] = spec.get("per_config") or {}
    unknown = set(per_config) - {p.stem for p in CONFIG_DIR.glob("*.yaml")}
    if unknown:
        raise SystemExit(f"unknown configs in per_config: {sorted(unknown)}")
    changed = []
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        header = []
        for ln in lines:
            if not ln.startswith("#"):
                break
            header.append(ln)
        data = yaml.safe_load(text)
        strategies = data.get("strategies")
        if isinstance(strategies, dict):
            for name, block in shared.items():
                if name in strategies:
                    strategies[name] = copy.deepcopy(block)
        if isinstance(strategies, dict) and "jev" in strategies and "jev_calibration" in spec:
            strategies["jev"]["calibration"] = copy.deepcopy(spec["jev_calibration"])
        data = merge(data, per_config.get(path.stem) or {})
        new = render(header, data)
        if new != text:
            changed.append(path)
            if not args.check:
                path.write_text(new, encoding="utf-8")
                load_settings(path)  # must still validate
    verb = "would change" if args.check else "wrote"
    print("\n".join(f"{verb} {p}" for p in changed) or "no change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
