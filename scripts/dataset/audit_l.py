"""Blind automated label audit of the phase-2 large-catalog splits (dev-L, test-L).

Parametrized copy of `audit.py` (which stays byte-identical): the same two-family design, the
same labelling policy text, the same per-case output fields, batches of 5 shuffled cases and the
same pre-declared adjudication rule (docs/dataset-card.md). Differences, all forced by phase 2:

- auditors run on Bedrock (`bedrock_chat.chat_json`, no OpenRouter): A `openai.gpt-oss-120b-1:0`
  (OpenAI family, reasoning effort low), B `deepseek.v3.2` (DeepSeek family), the same two
  families that audited test-v2; neither is a router nor the generator (Moonshot Kimi);
- auditors see the LARGE router-visible catalog (`mcp_server/tools_list_large.json`, 62 tools);
- Bedrock Converse has no strict JSON-schema mode, so the output schema is stated in the system
  prompt and each verdict is validated (and lightly normalized: `proposed_args` given as an
  object becomes name/value pairs) before it is kept; a missing/invalid verdict is re-asked by
  re-running `run` (done ids are skipped).

Fixes are applied to the split file (`label_audit` keeps the original gold); flagged cases keep
their gold (automated adjudication only, as in prereg-v1).

Usage:
  uv run python scripts/dataset/audit_l.py run --split dev_l [--auditor A|B] [--limit N]
  uv run python scripts/dataset/audit_l.py adjudicate --split dev_l
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from audit import (  # noqa: E402
    BATCH,
    POLICY,
    REVIEW_TEMPLATE,
    SYSTEM,
    agreement,
    case_block,
    norm_args,
    wilson,
)
from bedrock_chat import chat_json  # noqa: E402
from common_l import (  # noqa: E402
    ALL_TOOLS_L,
    TOOL_PARAMS_L,
    TOOL_SKILL_L,
    TOOLS_LIST_L,
    CaseL,
    ExpectedL,
    case_dict,
)
from openrouter import ledger  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
AUDIT = DATA / "audit"
SEED = 20261002
AUDITORS = {  # two families, neither Claude (routers) nor Moonshot (the generator)
    "A": "openai.gpt-oss-120b-1:0",
    "B": "deepseek.v3.2",
}
REGION = "sa-east-1"
MAX_TOKENS = 8000
TOOLS_ENUM = [*ALL_TOOLS_L, "__abstain__"]
SPLITS = ("dev_l", "test_l")
REQUIRED = [
    "id",
    "gold_acceptable",
    "wrong_tools",
    "missing_alternatives",
    "proposed_tools",
    "out_of_scope",
    "escalation_acceptable",
    "args_correct",
    "proposed_args",
    "rationale",
]
OUTPUT_FORMAT = """
Output: ONLY a JSON object {"cases": [...]}, one object per audited case, with exactly these keys:
"id" (string), "gold_acceptable" (boolean), "wrong_tools" (array of tool names),
"missing_alternatives" (array of tool names), "proposed_tools" (non-empty array of tool names,
best first), "out_of_scope" (boolean), "escalation_acceptable" (boolean), "args_correct"
(boolean), "proposed_args" (array of {"name": string, "value": string}), "rationale" (string).
Tool names must be exact catalog names or "__abstain__". No text outside the JSON."""
assert "{catalog}" in SYSTEM and POLICY in SYSTEM


def split_path(split: str) -> Path:
    return DATA / f"dataset_{split}.jsonl"


def load(path: Path) -> list[CaseL]:
    return [CaseL.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]


def split_cases(split: str) -> list[CaseL]:
    """Cases with the PRE-audit gold (what the auditors judged)."""
    return [
        c.model_copy(update={"expected": ExpectedL.model_validate(c.label_audit["original"])})
        if c.label_audit and c.label_audit.get("original")
        else c
        for c in load(split_path(split))
    ]


def catalog_text() -> str:
    tools = json.loads(TOOLS_LIST_L.read_text())["tools"]
    out = []
    for t in tools:
        params = list((t.get("inputSchema") or {}).get("properties") or {})
        out.append(
            f"### {t['name']} [skill {TOOL_SKILL_L[t['name']]}]\n{t.get('description', '').strip()}"
            f"\nparameters: {', '.join(params) or 'none'}"
        )
    return "\n\n".join(out)


def verdict_path(split: str, auditor: str) -> Path:
    return AUDIT / f"verdicts_{split}_{auditor}.jsonl"


def normalize_verdict(v: Any) -> Any:
    """Bedrock has no strict schema: coerce `proposed_args` given as an object into name/value
    pairs and stringify values. Anything else is validated, not repaired."""
    if not isinstance(v, dict):
        return v
    pa = v.get("proposed_args")
    if isinstance(pa, dict):
        v["proposed_args"] = [{"name": str(k), "value": str(x)} for k, x in pa.items()]
    elif isinstance(pa, list):
        v["proposed_args"] = [
            {"name": str(p["name"]), "value": "" if p.get("value") is None else str(p["value"])}
            for p in pa
            if isinstance(p, dict) and "name" in p
        ]
    return v


def valid_verdict(v: Any, cid: str) -> bool:
    if not (isinstance(v, dict) and v.get("id") == cid and set(REQUIRED) <= set(v)):
        return False
    bools = ("gold_acceptable", "out_of_scope", "escalation_acceptable", "args_correct")
    lists = ("wrong_tools", "missing_alternatives", "proposed_tools")
    return (
        all(isinstance(v[k], bool) for k in bools)
        and all(isinstance(v[k], list) and set(v[k]) <= set(TOOLS_ENUM) for k in lists)
        and bool(v["proposed_tools"])
        and isinstance(v["proposed_args"], list)
    )


# ------------------------------------------------------------------ run


def run(split: str, auditor: str, max_cost: float, limit: int | None = None) -> None:
    model = AUDITORS[auditor]
    cases = split_cases(split)
    path = verdict_path(split, auditor)
    done = {json.loads(x)["id"] for x in path.read_text().splitlines()} if path.exists() else set()
    todo = [c for c in cases if c.id not in done]
    random.Random(f"{SEED}-{split}").shuffle(todo)  # mix categories inside a batch
    todo = todo[:limit] if limit else todo
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    system = SYSTEM.replace("{catalog}", catalog_text()) + "\n" + OUTPUT_FORMAT
    led = ledger()
    spent = 0.0
    print(f"{split} auditor {auditor} ({model}): {len(todo)} cases, {len(batches)} calls")

    def one(batch: list[CaseL]) -> tuple[list[CaseL], Any, dict[str, Any]]:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": "Audit these cases:\n"
                    + json.dumps([case_block(c) for c in batch], ensure_ascii=False, indent=1),
                },
            ],
            "max_tokens": MAX_TOKENS,
        }
        parsed, usage = chat_json(
            body, purpose=f"dataset_{split}_audit_{auditor}", led=led, region=REGION
        )
        return batch, parsed, usage

    with path.open("a", encoding="utf-8") as out, ThreadPoolExecutor(6) as ex:
        for batch, parsed, usage in ex.map(one, batches):
            spent += usage["cost"]
            rows = (parsed or {}).get("cases", []) if isinstance(parsed, dict) else []
            got = {v.get("id"): normalize_verdict(v) for v in rows if isinstance(v, dict)}
            for c in batch:
                v = got.get(c.id)
                if not valid_verdict(v, c.id):
                    print(f"  missing/invalid verdict {c.id}")
                    continue
                v = {k: v[k] for k in REQUIRED}
                v["auditor"], v["model"] = auditor, model
                out.write(json.dumps(v, ensure_ascii=False) + "\n")
            out.flush()
            if spent > max_cost:
                raise SystemExit(f"audit cost ${spent:.4f} > cap ${max_cost}")
    n = len(path.read_text().splitlines())
    print(f"{split}/{auditor}: {n}/{len(cases)} verdicts, cost ${spent:.4f}")


# ------------------------------------------------------------------ adjudication


def adjudicate_case(c: CaseL, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """`audit.adjudicate_case` (same rule) with the large-catalog schema."""
    reasons: list[str] = []
    tools = list(c.expected.acceptable_tools)
    args = dict(c.expected.args)
    changed = False
    if a["gold_acceptable"] and b["gold_acceptable"]:
        pass
    elif (
        not a["gold_acceptable"]
        and not b["gold_acceptable"]
        and set(a["proposed_tools"]) == set(b["proposed_tools"])
        and a["proposed_tools"][0] == b["proposed_tools"][0]
    ):
        tools, changed = list(dict.fromkeys(a["proposed_tools"])), True
        reasons.append("tools_fixed")
    else:
        reasons.append("tools_disagree")
    if a["args_correct"] and b["args_correct"]:
        pass
    elif (
        not a["args_correct"]
        and not b["args_correct"]
        and norm_args(a["proposed_args"]) == norm_args(b["proposed_args"])
    ):
        args = {p["name"]: p["value"] for p in a["proposed_args"] if p["value"].strip()}
        changed = True
        reasons.append("args_fixed")
    else:
        reasons.append("args_disagree")
    flagged = any(r.endswith("disagree") for r in reasons)
    new: ExpectedL | None = None
    if changed and not flagged:
        try:
            skills = list(dict.fromkeys(TOOL_SKILL_L[t] for t in tools))
            new = ExpectedL(acceptable_skills=skills, acceptable_tools=tools, args=args)
            params = set()
            for t in tools:
                params |= set(TOOL_PARAMS_L.get(t, []))
            if set(new.args) - params:
                raise ValueError("args not parameters of the fixed tools")
        except (ValueError, KeyError):
            reasons.append("fix_invalid")
            flagged, new = True, None
    common_missing = sorted(set(a["missing_alternatives"]) & set(b["missing_alternatives"]))
    return {
        "id": c.id,
        "decision": "flagged" if flagged else ("fixed" if new is not None else "keep"),
        "reasons": reasons,
        "fixed_expected": new.model_dump() if new is not None else None,
        "both_missing_alternatives": common_missing,
    }


def split_stats(cases: list[CaseL], va: dict[str, dict], vb: dict[str, dict]) -> dict[str, Any]:
    """`audit.split_stats` with the phase-2 auditors."""
    ids = [c.id for c in cases if c.id in va and c.id in vb]
    by_id = {c.id: c for c in cases}
    A = [va[i] for i in ids]
    B = [vb[i] for i in ids]
    gold = [by_id[i].expected.acceptable_tools for i in ids]
    out: dict[str, Any] = {"n_cases": len(cases), "n_both_verdicts": len(ids)}
    out["between_auditors"] = {
        f: agreement([x[f] for x in A], [y[f] for y in B])
        for f in ("gold_acceptable", "args_correct", "out_of_scope", "escalation_acceptable")
    }
    out["between_auditors"]["first_proposed_tool"] = agreement(
        [x["proposed_tools"][0] for x in A], [y["proposed_tools"][0] for y in B]
    )
    per: dict[str, Any] = {}
    for name, V in (("A", A), ("B", B)):
        k = sum(v["gold_acceptable"] for v in V)
        per[name] = {
            "model": AUDITORS[name],
            "gold_acceptable_rate": round(k / len(V), 4) if V else None,
            "gold_acceptable_ci95": wilson(k, len(V)),
            "args_correct_rate": round(sum(v["args_correct"] for v in V) / len(V), 4)
            if V
            else None,
            "vs_gold_out_of_scope": agreement(
                [v["out_of_scope"] for v in V], ["__abstain__" in g for g in gold]
            ),
            "vs_gold_escalation": agreement(
                [v["escalation_acceptable"] for v in V], ["escalate_to_human" in g for g in gold]
            ),
            "vs_gold_first_tool": agreement(
                [v["proposed_tools"][0] for v in V], [g[0] for g in gold]
            ),
            "first_proposed_in_gold_rate": round(
                sum(v["proposed_tools"][0] in g for v, g in zip(V, gold, strict=True)) / len(V), 4
            )
            if V
            else None,
        }
    out["auditor_vs_gold"] = per
    cats = sorted({by_id[i].category for i in ids})
    out["gold_acceptable_by_category"] = {
        cat: {
            "n": sum(by_id[i].category == cat for i in ids),
            "A": sum(va[i]["gold_acceptable"] for i in ids if by_id[i].category == cat),
            "B": sum(vb[i]["gold_acceptable"] for i in ids if by_id[i].category == cat),
            "both": sum(
                va[i]["gold_acceptable"] and vb[i]["gold_acceptable"]
                for i in ids
                if by_id[i].category == cat
            ),
        }
        for cat in cats
    }
    return out


def read_verdicts(split: str, auditor: str) -> dict[str, dict[str, Any]]:
    path = verdict_path(split, auditor)
    if not path.exists():
        return {}
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    return {r["id"]: r for r in rows}  # last verdict per id wins


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adjudicate(split: str) -> None:
    cases = split_cases(split)
    va, vb = read_verdicts(split, "A"), read_verdicts(split, "B")
    missing = [c.id for c in cases if c.id not in va or c.id not in vb]
    if missing:
        raise SystemExit(f"{split}: {len(missing)} cases lack a verdict, e.g. {missing[:3]}")
    results = [adjudicate_case(c, va[c.id], vb[c.id]) for c in cases]
    stats = split_stats(cases, va, vb)
    stats["decisions"] = dict(Counter(r["decision"] for r in results))
    stats["decisions_by_category"] = {
        cat: dict(
            Counter(r["decision"] for r, c in zip(results, cases, strict=True) if c.category == cat)
        )
        for cat in sorted({c.category for c in cases})
    }
    stats["both_missing_alternatives_cases"] = sum(
        bool(r["both_missing_alternatives"]) for r in results
    )
    adj = AUDIT / f"adjudication_{split}.jsonl"
    with adj.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    apply_to_split(split, cases, results)
    summary_path = AUDIT / "summary_l.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {"splits": {}}
    summary["auditors"] = AUDITORS
    summary["provider"] = f"bedrock:{REGION}"
    summary["splits"][split] = stats
    summary.setdefault("dataset_sha256", {})[split] = sha256(split_path(split))
    summary.setdefault("files_sha256", {}).update(
        {p.name: sha256(p) for p in (verdict_path(split, "A"), verdict_path(split, "B"), adj)}
    )
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    review = [
        {
            "case": case_block(c) | {"category": c.category},
            "A": va[c.id],
            "B": vb[c.id],
            "reasons": r["reasons"],
        }
        for c, r in zip(cases, results, strict=True)
        if r["decision"] == "flagged"
    ]
    write_review_html(split, review, summary["dataset_sha256"][split])
    print(
        json.dumps(
            {k: v for k, v in stats.items() if k in ("decisions", "between_auditors")}, indent=1
        )
    )


def apply_to_split(split: str, cases: list[CaseL], results: list[dict[str, Any]]) -> None:
    """Write the adjudication into the split: fixes replace the gold (original kept)."""
    out = []
    for c, r in zip(cases, results, strict=True):
        audit: dict[str, object] = {
            "decision": r["decision"],
            "reasons": r["reasons"],
            "auditors": [AUDITORS["A"], AUDITORS["B"]],
        }
        if r["both_missing_alternatives"]:
            audit["both_missing_alternatives"] = r["both_missing_alternatives"]
        expected = c.expected  # split_cases already restored the pre-audit gold
        if r["fixed_expected"] is not None:
            audit["original"] = c.expected.model_dump()
            expected = ExpectedL.model_validate(r["fixed_expected"])
        out.append(c.model_copy(update={"expected": expected, "label_audit": audit}))
    with split_path(split).open("w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(case_dict(c), ensure_ascii=False, separators=(",", ":")) + "\n")


def write_review_html(split: str, review: list[dict[str, Any]], sha: str) -> None:
    data = json.dumps(
        {
            "dataset_sha256": sha,
            "auditors": AUDITORS,
            "tools": TOOLS_ENUM,
            "splits": {split: review},
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    page = (
        REVIEW_TEMPLATE.replace("__DATA__", data)
        .replace("__GENERATED__", html.escape(datetime.now(UTC).isoformat(timespec="seconds")))
        .replace("data/dataset_test_v2.jsonl", f"data/dataset_{split}.jsonl")
    )
    (AUDIT / f"review_{split}.html").write_text(page, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--split", choices=SPLITS, required=True)
    r.add_argument("--auditor", choices=[*AUDITORS, "all"], default="all")
    r.add_argument("--max-cost", type=float, default=1.5)
    r.add_argument("--limit", type=int, default=None, help="pilot: first N shuffled cases")
    a = sub.add_parser("adjudicate")
    a.add_argument("--split", choices=SPLITS, required=True)
    args = ap.parse_args()
    AUDIT.mkdir(parents=True, exist_ok=True)
    if args.cmd == "run":
        for name in AUDITORS if args.auditor == "all" else [args.auditor]:
            run(args.split, name, args.max_cost, args.limit)
    else:
        adjudicate(args.split)


if __name__ == "__main__":
    main()
