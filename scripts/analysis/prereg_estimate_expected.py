"""Expected (realistic) cost per manifest entry, next to the a-priori upper bound of
`study estimate` (results/freeze/estimate_apriori.tsv). Per-case costs are dev measurements:
routing $/1k from config/prompt_selection.yaml (original cost, cache counted as paid), e2e $/turn
from the dev e2e runs (E0 5.71, routed 3.63 per 349 turns) x 1.3 safety. Cache sharing: the
shadow pass pays Sonnet + Jev; E4/E5/E7-E9 pay only tool-stage misses (10% of turns assumed).
"""

import csv
import sys

import yaml

sel = yaml.safe_load(open("config/prompt_selection.yaml"))["models"]
SON = sel["global.anthropic.claude-sonnet-5"]["canonical"]["cost_per_1k"] / 1000
HAI = sel["global.anthropic.claude-haiku-4-5-20251001-v1:0"]["canonical"]["cost_per_1k"] / 1000
JEV = sel["typesafe/jev-router"]["canonical"]["cost_per_1k"] / 1000
P6C = 0.60 / 1000
E0_TURN, ROUTED_TURN, SAFETY, MISS, TOOL_SHARE = 5.714 / 349, 3.63 / 349, 1.3, 0.10, 0.55


def expected(name: str, mode: str, n: int, reps: int) -> tuple[float, float]:
    t = n * reps
    if name.startswith("lat-"):
        s = name.split("-")[1]
        return {
            "sonnet": (t * SON, 0),
            "haiku": (t * HAI, 0),
            "jev": (0, t * JEV),
            "e7": (0, t * JEV * 0.7),
            "e8": (t * SON * 0.8, 0),
            "e9": (t * SON * 0.5, t * JEV * 0.7),
        }.get(s, (0, 0))
    if mode == "e2e":
        per = E0_TURN if "e0-native" in name else ROUTED_TURN
        jev = t * JEV * MISS if ("e7" in name or "e9" in name) else 0
        return t * per * SAFETY, jev
    if name == "v2-shadow-tuned-routing-r3":
        return t * SON, t * JEV
    if name in ("v2-e5-sonnet-canonical-routing-r3", "v2-e8-tuned-routing-r3"):
        return t * SON * MISS * TOOL_SHARE, 0
    if name in ("v2-e4-jev-canonical-routing-r3", "v2-e7-tuned-routing-r3"):
        return 0, t * JEV * MISS * TOOL_SHARE
    if name == "v2-e9-tuned-routing-r3":
        return 0, 0
    if "haiku" in name:
        if name.endswith("rep2-60"):
            return n * HAI, 0  # rep 2 only (rep 1 cached)
        if name.endswith("-zero"):
            return 0, 0
        return t * HAI, 0
    if "rq5" in name:
        if name.endswith("-zero"):
            return 0, 0
        if "sonnet" in name:
            return t * SON, 0
        if "jev" in name:
            return 0, t * JEV
    if name.startswith("x-e4-jev-p6c"):
        return 0, t * P6C
    return 0, 0


rows = list(csv.reader(open(sys.argv[1]), delimiter="\t"))
tb = to = ab = ao = 0.0
print(
    "| prio | run | mode | cases x reps | a priori bedrock | a priori openrouter"
    " | expected bedrock | expected openrouter |"
)
print("|---|---|---|---|---|---|---|---|")
for prio, name, mode, nr, b, o in rows:
    n, reps = map(int, nr.split("x"))
    eb, eo = expected(name, mode, n, reps)
    tb, to, ab, ao = tb + eb, to + eo, ab + float(b), ao + float(o)
    if float(b) or float(o) or eb or eo:
        print(
            f"| {prio} | {name} | {mode} | {nr} | {float(b):.2f} | {float(o):.2f}"
            f" | {eb:.2f} | {eo:.2f} |"
        )
print(
    f"| | **total ({len(rows)} entries; free entries omitted)** | | "
    f"| **{ab:.2f}** | **{ao:.2f}** | **{tb:.2f}** | **{to:.2f}** |"
)
