"""Write the router prompt selection (docs/prompt-apex.md) into the experiment configs.

Usage:
  uv run python scripts/analysis/apply_prompt_selection.py [--selection <file>]

`config/prompt_selection.yaml` maps each router model to its variant and calibration maps per
track (`canonical`, `tuned`). For every experiment config, every LLM / Jev strategy block gets
`prompt_track`, `prompt_variant` and `calibration` of its model on the config's track:

- tuned track: the cascades (E7-E9) and the `*_tuned.yaml` copies of E4, E5, E6, E6b
  (created here from the canonical file);
- canonical track: every other config.

Blocks are rewritten in block style; the rest of each file is left byte for byte.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

EXPERIMENTS = Path("config/experiments")
TUNED_COPIES = (
    "e4_jev",
    "e5_llm_sonnet",
    "e6_llm_haiku",
    "e6b_llm_qwen3_local",
)
CASCADES = ("e7_regex_jev", "e8_regex_llm", "e9_regex_jev_llm")
BLOCK = re.compile(r"^  (llm(?:_[a-z0-9]+)*|jev):.*\n(?:(?:    |\s*#).*\n)*", re.MULTILINE)
PROMPT_KEYS = ("prompt_track", "prompt_variant", "calibration")


def flow(value: Any) -> str:
    """One-line YAML of a value (scalar, list or map)."""
    text = yaml.safe_dump({"_": value}, default_flow_style=True, width=10_000, sort_keys=False)
    return text.strip()[len("{_: ") : -1]


def render(name: str, cfg: dict[str, Any], comment: str = "") -> str:
    lines = [f"  {name}:" + (f"  {comment}" if comment else "")]
    for key, value in cfg.items():
        if key == "calibration":
            lines.append("    calibration:            # isotonic raw -> P(correct), fitted on dev")
            for level, cal in value.items():
                lines.append(f"      {level}: {flow(cal)}")
        else:
            lines.append(f"    {key}: {flow(value)}")
    return "\n".join(lines) + "\n"


def apply(text: str, track: str, selection: dict[str, Any]) -> str:
    strategies = yaml.safe_load(text).get("strategies") or {}

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        first = m.group(0).split("\n", 1)[0]
        comment = first[first.index("#") :] if "#" in first else ""
        cfg = {k: v for k, v in (strategies.get(name) or {}).items() if k not in PROMPT_KEYS}
        chosen = (selection.get(cfg.get("model")) or {}).get(track)
        if chosen is None:
            return m.group(0)
        cfg["prompt_track"] = track
        cfg["prompt_variant"] = chosen["variant"]
        if chosen.get("calibration"):
            cfg["calibration"] = chosen["calibration"]
        return render(name, cfg, comment)

    return BLOCK.sub(sub, text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--selection", default="config/prompt_selection.yaml")
    args = ap.parse_args()
    selection = yaml.safe_load(Path(args.selection).read_text(encoding="utf-8"))["models"]
    for path in sorted(EXPERIMENTS.glob("*.yaml")):
        if path.stem.endswith("_tuned"):
            continue
        text = path.read_text(encoding="utf-8")
        track = "tuned" if path.stem in CASCADES else "canonical"
        path.write_text(apply(text, track, selection), encoding="utf-8")
        if path.stem in TUNED_COPIES:
            tuned = EXPERIMENTS / f"{path.stem}_tuned.yaml"
            header = f"# Tuned prompt track of {path.name} (docs/prompt-apex.md)\n"
            tuned.write_text(header + apply(text, "tuned", selection), encoding="utf-8")
        print(f"{path.name}: {track}")


if __name__ == "__main__":
    main()
