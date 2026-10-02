"""Check that every local markdown link and image in the study docs resolves.

Usage: uv run python scripts/analysis/final_linkcheck.py [repo root, default: this repo]
Covers README.md, README.pt-BR.md, docs/study-results.md and estudos/*.md (code fences skipped).
"""

import pathlib
import re
import sys

root = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2]
)
files = [
    root / "README.md",
    root / "README.pt-BR.md",
    root / "docs/study-results.md",
    *sorted((root / "estudos").glob("*.md")),
]
bad = n = 0
for f in files:
    txt = re.sub(r"```.*?```", "", f.read_text(encoding="utf-8"), flags=re.S)
    for m in re.finditer(r"!?\[[^\]]*\]\(([^)\s]+)\)", txt):
        t = m.group(1)
        if t.startswith(("http", "#", "mailto:")):
            continue
        n += 1
        if not (f.parent / t.split("#")[0]).exists():
            bad += 1
            print(f"BROKEN {f.relative_to(root)} -> {t}")
print(f"checked {n} local links/images in {len(files)} files; broken {bad}")
sys.exit(1 if bad else 0)
