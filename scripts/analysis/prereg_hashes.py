"""Write config_hash / prompt_hash into every entry of a manifest (in place) and print a table.

uv run python scripts/analysis/prereg_hashes.py config/study_manifest.yaml
"""

import re
import sys
from pathlib import Path

import yaml

from routing_study.eval.manifest import load_manifest, load_run_settings
from routing_study.eval.runner import config_hash, run_prompt_hash

path = Path(sys.argv[1])
m = load_manifest(path)
ph = run_prompt_hash()
hashes = {}
for r in m.runs:
    s = load_run_settings(r)
    hashes[r.name] = config_hash(s)
text = path.read_text(encoding="utf-8")
text = re.sub(r", config_hash: \w+, prompt_hash: \w+", "", text)
text = re.sub(r"\n    config_hash: \w+\n    prompt_hash: \w+", "", text)
out = []
for line in text.splitlines(keepends=True):
    mf = re.match(r"(\s*- \{ name: )([\w.-]+)(, .*)", line)
    mb = re.match(r"(\s*- name: )([\w.-]+)\s*$", line)
    if mf and mf.group(2) in hashes:
        n = mf.group(2)
        line = f"{mf.group(1)}{n}, config_hash: {hashes[n]}, prompt_hash: {ph}{mf.group(3)}\n"
    elif mb and mb.group(2) in hashes:
        n = mb.group(2)
        line += f"    config_hash: {hashes[n]}\n    prompt_hash: {ph}\n"
    out.append(line)
path.write_text("".join(out), encoding="utf-8")
m2 = yaml.safe_load(path.read_text(encoding="utf-8"))
missing = [r["name"] for r in m2["runs"] if not r.get("config_hash")]
assert not missing, missing
print("| run | config | config_hash | prompt_hash |\n|---|---|---|---|")
for r in m.runs:
    print(f"| {r.name} | {r.config.name} | {hashes[r.name]} | {ph} |")
