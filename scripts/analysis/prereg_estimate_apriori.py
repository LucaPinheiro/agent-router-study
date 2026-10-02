"""`study estimate` for every manifest entry (a priori, no-cache upper bound), one CLI call per
distinct (config, split, mode, reps, n) - RQ5 overrides do not change the a-priori cost."""

import re
import subprocess
from pathlib import Path

from routing_study.eval.manifest import load_manifest, select_cases

m = load_manifest(Path("config/study_manifest.yaml"))
seen = {}
for r in m.ordered():
    split = m.split_of(r)
    n = len(select_cases(r, split))
    key = (str(r.config), split, r.mode, r.reps, n)
    if key not in seen:
        cmd = [
            "uv",
            "run",
            "study",
            "estimate",
            "-c",
            str(r.config),
            "--split",
            split,
            "--mode",
            r.mode,
            "--reps",
            str(r.reps),
        ]
        if r.cases.limit or r.cases.ids_file:
            cmd += ["--limit", str(n)]
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        prov = dict(re.findall(r"^\s+(bedrock|openrouter|ollama)\s+\$([\d.]+)", out, re.M))
        seen[key] = prov
    prov = seen[key]
    print(
        "\t".join(
            [str(r.priority), r.name, r.mode, f"{n}x{r.reps}"]
            + [prov.get("bedrock", "0"), prov.get("openrouter", "0")]
        ),
        flush=True,
    )
