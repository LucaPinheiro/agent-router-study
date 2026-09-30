"""Generate the confirmatory split test-v2 (`data/dataset_test_v2.jsonl`).

Same generator model, temperature, reasoning effort, prompt templates and label filters as
`generate.py` (test-v1), with a NEW seed and three additions:

1. Stratified jobs: the exact test-v1 category quotas (105/87/70/35/35/17) and a per-tool
   quota inside direto/parafrase/multiturno, so every tool gets 12-13 single-label cases.
2. Mock-DB-aware slots: each item's customer and the order ids offered to the generator are
   drawn among orders whose state (`mcp_server/MOCK_DB_NOTES.md` archetype) lets the target tool
   complete; mentioning any other order rejects the item.
3. Dedupe/leakage: exact/normalized + `SequenceMatcher` >= 0.9 against the 500 existing cases
   and every router-visible catalog text unit, semantic cosine >= 0.9 (local
   qwen3-embedding) against the same sets, and >= 0.85 lexical within test-v2. Rejected slots
   are regenerated (up to --rounds rounds).

Adversarial label policy (data/README.md): a `tool_by_name` request accepts the named tool
first (the generator's labels stay as alternatives); a `decoy` item must not accept the named
tool; injection/abuse must be `__abstain__`/`escalate_to_human`.

Usage: uv run python scripts/dataset/generate_v2.py [--max-cost 2.5]
test-v1 content is never shown to the generator; it is used only as a dedupe reference.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))
import overlap  # noqa: E402
from common import ALL_TOOLS, CATEGORIES, TOOL_SKILL, Case, case_dict, case_text  # noqa: E402
from generate import (  # noqa: E402
    ADV_KINDS,
    AMBIG_GROUPS,
    OOS_TOPICS,
    TOOL_PARAMS,
    build_prompt,
    labels_ok,
    load_env,
    slots,
    to_case,
)
from openrouter import chat_json, credits, ledger  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
AUDIT = DATA / "audit"
OUT = DATA / "dataset_test_v2.jsonl"
META = DATA / "generation_meta_v2.json"
LOG = AUDIT / "generation_v2_log.jsonl"
SEED = 20260930  # test-v1 generation used 20260929
MODEL = "google/gemini-2.5-flash"
TEMPERATURE = 0.9
QUOTA = {  # test-v1 counts per category
    "direto": 105,
    "parafrase": 87,
    "ambiguo": 70,
    "multiturno": 35,
    "fora_escopo": 35,
    "adversarial": 17,
}
WITHIN_LEXICAL = 0.85  # same as generate.py
MAX_PER_CALL = 12
ORDER_RE = re.compile(r"\bO\d{4}\b")
NOTES = ROOT / "mcp_server" / "MOCK_DB_NOTES.md"
MOCK_DB = ROOT / "mcp_server" / "src" / "mcp_server" / "mock_db.json"


# ------------------------------------------------------------------ mock DB satisfiability


def _mock_module() -> Any:
    path = ROOT / "mcp_server" / "scripts" / "generate_mock_db.py"
    spec = importlib.util.spec_from_file_location("generate_mock_db", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def order_compat() -> dict[str, set[str]]:
    """order id -> tools that complete on its mock-DB state (MOCK_DB_NOTES archetype table)."""
    mod = _mock_module()
    arch = dict(re.findall(r"^\| (O\d{4}) \| ([a-z_]+) \|", NOTES.read_text(), re.M))
    return {o: mod.compatible_tools(mod.ARCHETYPES[a]) for o, a in sorted(arch.items())}


def order_owner(order_id: str) -> str:
    return f"C{(int(order_id[1:]) - 1) // 3 + 1:03d}"


def referenced_orders(c: Case) -> set[str]:
    ids = set(ORDER_RE.findall(" ".join(t.content for t in c.turns)))
    if c.expected.args.get("order_id"):
        ids.add(str(c.expected.args["order_id"]))
    return ids


def satisfiability(c: Case, compat: dict[str, set[str]]) -> dict[str, Any]:
    """Per referenced order: does the first / any acceptable tool complete on its state?"""
    tools = c.expected.acceptable_tools
    rows = []
    for o in sorted(referenced_orders(c)):
        ok = compat.get(o, set())
        rows.append({"order": o, "first_ok": tools[0] in ok, "any_ok": any(t in ok for t in tools)})
    return {"orders": rows, "conflict": any(not r["any_ok"] for r in rows)}


# ------------------------------------------------------------------ jobs


def tool_quotas(rng: random.Random) -> dict[str, dict[str, int]]:
    """Per-category per-tool quotas; the remainders rotate over one shuffled tool order so the
    single-label total per tool differs by at most one."""
    order = list(ALL_TOOLS)
    rng.shuffle(order)
    out: dict[str, dict[str, int]] = {}
    pos = 0
    for cat in ("direto", "parafrase", "multiturno"):
        base, extra = divmod(QUOTA[cat], len(order))
        q = dict.fromkeys(ALL_TOOLS, base)
        for i in range(extra):
            q[order[(pos + i) % len(order)]] += 1
        pos += extra
        out[cat] = q
    return out


def split_even(total: int, keys: list[Any]) -> list[int]:
    base, extra = divmod(total, len(keys))
    return [base + (1 if i < extra else 0) for i in range(len(keys))]


def build_jobs(rng: random.Random) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    tq = tool_quotas(rng)
    for cat in CATEGORIES:
        if cat in tq:
            targets: list[Any] = list(ALL_TOOLS)
            quotas = [tq[cat][t] for t in ALL_TOOLS]
        elif cat == "ambiguo":
            targets, quotas = list(AMBIG_GROUPS), split_even(QUOTA[cat], AMBIG_GROUPS)
        elif cat == "fora_escopo":
            targets, quotas = list(OOS_TOPICS), split_even(QUOTA[cat], OOS_TOPICS)
        else:  # adversarial: tool_by_name first gets the remainder
            targets, quotas = list(ADV_KINDS), split_even(QUOTA[cat], ADV_KINDS)
        for t, q in zip(targets, quotas, strict=True):
            label = t if isinstance(t, str) else (t[1] if cat == "adversarial" else t[0][:40])
            jobs.append({"cat": cat, "target": t, "quota": q, "label": label})
    assert sum(j["quota"] for j in jobs) == sum(QUOTA.values())
    return jobs


def job_slots(
    job: dict[str, Any], n: int, rng: random.Random, compat: dict[str, set[str]]
) -> list[tuple[str, list[str]]]:
    """Customer + the order ids offered to the generator for each item."""
    cat, target = job["cat"], job["target"]
    if cat in ("fora_escopo", "adversarial"):
        return slots(n, rng)  # as in generate.py (adversarial target tool unknown upfront)
    tools = list(target[1]) if cat == "ambiguo" else [target]
    good = [o for o, ok in compat.items() if tools[0] in ok] or [
        o for o, ok in compat.items() if any(t in ok for t in tools)
    ]
    out = []
    for _ in range(n):
        o = rng.choice(good)
        cust = order_owner(o)
        k = int(cust[1:])
        listed = [x for x in (f"O{3 * k - 3 + i:04d}" for i in (1, 2, 3)) if x in good]
        out.append((cust, listed))
    return out


# ------------------------------------------------------------------ labels


def reject_reason(cat: str, target: Any, item: dict[str, Any], slot: tuple[str, list[str]]) -> str:
    try:
        tools = list(dict.fromkeys(item["acceptable_tools"]))
        last = item["turns"][-1]["content"]
    except (KeyError, TypeError, IndexError):
        return "schema"
    if not labels_ok(cat, target, tools, last):
        return "label_spec"
    if not set(item.get("args") or {}) <= {p for t in tools for p in TOOL_PARAMS.get(t, [])}:
        return "args_param"
    if set(ORDER_RE.findall(json.dumps(item, ensure_ascii=False))) - set(slot[1]):
        return "order_not_offered"
    return "schema"


def apply_adversarial_policy(c: Case, kind: str) -> Case | None:
    last = c.turns[-1].content
    named = [t for t in ALL_TOOLS if re.search(rf"\b{t}\b", last)]
    tools = list(c.expected.acceptable_tools)
    if kind == "tool_by_name":
        if len(named) != 1:
            return None
        tools = [named[0], *[t for t in tools if t != named[0]]]
    elif kind == "decoy" and (not named or set(named) & set(tools)):
        return None
    skills = list(dict.fromkeys(TOOL_SKILL[t] for t in tools))
    exp = {"acceptable_skills": skills, "acceptable_tools": tools, "args": c.expected.args}
    return c.model_copy(update={"expected": c.expected.model_validate(exp)})


def make_case(
    job: dict[str, Any], item: dict[str, Any], slot: tuple[str, list[str]]
) -> tuple[Case | None, str]:
    cat, target = job["cat"], job["target"]
    c = to_case(cat, target, item, slot, "tmp")
    if c is None:
        return None, reject_reason(cat, target, item, slot)
    if cat == "adversarial":
        c = apply_adversarial_policy(c, target[1])
        if c is None:
            return None, "adversarial_policy"
    try:
        c = Case.model_validate({**case_dict(c), "source": "synthetic_v2", "reviewed": False})
    except ValidationError:
        return None, "schema"
    return c, ""


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-cost", type=float, default=2.5, help="USD cap for generation calls")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--oversample", type=float, default=1.6)
    args = ap.parse_args()
    key = load_env()
    rng = random.Random(SEED)
    led = ledger()
    compat = order_compat()
    AUDIT.mkdir(parents=True, exist_ok=True)

    def load(name: str) -> list[Case]:
        return [Case.model_validate_json(x) for x in (DATA / name).read_text().splitlines() if x]

    existing = load("seed.jsonl") + load("synthetic.jsonl")  # = dev + test-v1 (500)
    case_refs = [case_text(c) for c in existing]
    units = overlap.catalog_units()
    emb = overlap.Embedder()
    print(f"embedding {len(existing)} cases + {len(units)} catalog units ...", flush=True)
    ref_vecs = emb([overlap.semantic_text(c) for c in existing] + units)

    jobs = build_jobs(rng)
    for j in jobs:
        j["rng"] = random.Random(rng.random())
        j["accepted"] = []
    accepted_texts: list[str] = []
    rejects: Counter[str] = Counter()
    prompts: list[str] = []
    total_cost = 0.0
    calls = 0
    log = LOG.open("w", encoding="utf-8")

    with httpx.Client() as client:
        before = credits(client, key)
        print(f"OpenRouter total_usage before: {before['total_usage']:.4f}", flush=True)
        for rnd in range(1, args.rounds + 1):
            todo = []
            for j in jobs:
                need = j["quota"] - len(j["accepted"])
                if need <= 0:
                    continue
                factor = 4.0 if j["cat"] == "adversarial" else args.oversample
                n = max(2, round(need * factor))
                while n > 0:
                    m = min(n, MAX_PER_CALL)
                    todo.append((j, m))
                    n -= m
            if not todo:
                break
            if total_cost > args.max_cost:
                raise SystemExit(f"generation cost ${total_cost:.4f} > cap ${args.max_cost}")
            print(f"round {rnd}: {len(todo)} calls", flush=True)

            tasks = []  # slots and prompts drawn sequentially (per-job RNG, reproducible)
            for j, m in todo:
                sl = job_slots(j, m, j["rng"], compat)
                tasks.append((j, sl, build_prompt(j["cat"], j["target"], m, sl)))
            prompts.extend(t[2] for t in tasks)

            def run(task: tuple[dict[str, Any], list, str]) -> tuple[dict, list, list, dict]:
                j, sl, prompt = task
                body = {
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": TEMPERATURE,
                    "response_format": {"type": "json_object"},
                    "reasoning": {"effort": "low"},
                }
                parsed, usage = chat_json(
                    client, key, body, purpose="dataset_v2_generation", led=led
                )
                items = parsed.get("items", []) if isinstance(parsed, dict) else []
                return j, sl, items if isinstance(items, list) else [], usage

            with ThreadPoolExecutor(12) as ex:
                results = list(ex.map(run, tasks))

            cands: list[tuple[dict[str, Any], Case]] = []
            for j, sl, items, usage in results:
                calls += 1
                total_cost += usage["cost"]
                for i, item in enumerate(items[: len(sl)]):
                    c, why = (
                        make_case(j, item, sl[i]) if isinstance(item, dict) else (None, "schema")
                    )
                    if c is None:
                        rejects[why] += 1
                        log.write(
                            json.dumps(
                                {"round": rnd, "job": j["label"], "reject": why, "item": item},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        continue
                    cands.append((j, c))
            vecs = emb([overlap.semantic_text(c) for _, c in cands])
            sims, idx = overlap.max_cosine(vecs, ref_vecs)
            order = list(range(len(cands)))
            rng.shuffle(order)
            for k in order:
                j, c = cands[k]
                if len(j["accepted"]) >= j["quota"]:
                    rejects["surplus"] += 1
                    continue
                why = overlap.lexical_hit(c, case_refs, units)
                if why is None and sims[k] >= overlap.SEMANTIC_THRESHOLD:
                    ref = "case" if idx[k] < len(existing) else "catalog"
                    why = f"semantic_{ref}:{sims[k]:.3f}"
                if why is None:
                    r, _ = overlap.max_ratio(case_text(c), accepted_texts)
                    if r > WITHIN_LEXICAL:
                        why = f"lexical_within:{r:.3f}"
                if why is not None:
                    rejects[why.split(":")[0]] += 1
                    log.write(
                        json.dumps(
                            {"round": rnd, "job": j["label"], "reject": why, "case": case_dict(c)},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    continue
                j["accepted"].append(c)
                accepted_texts.append(case_text(c))
            got = sum(len(j["accepted"]) for j in jobs)
            print(
                f"round {rnd}: accepted {got}/{sum(QUOTA.values())} cost ${total_cost:.4f} "
                f"rejects {dict(rejects)}",
                flush=True,
            )
        after = credits(client, key)
    log.close()

    short = {
        j["label"]: j["quota"] - len(j["accepted"]) for j in jobs if len(j["accepted"]) < j["quota"]
    }
    if short:
        raise SystemExit(f"quota not met after {args.rounds} rounds: {short}")

    out: list[Case] = []
    for cat in CATEGORIES:
        cases = [c for j in jobs if j["cat"] == cat for c in j["accepted"]]
        for n, c in enumerate(cases, 1):
            out.append(c.model_copy(update={"id": f"v2-{cat}-{n:03d}"}))
    with OUT.open("w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(case_dict(c), ensure_ascii=False, separators=(",", ":")) + "\n")

    sat = {c.id: satisfiability(c, compat) for c in out}
    per_tool_any = Counter(t for c in out for t in c.expected.acceptable_tools)
    per_tool_first = Counter(c.expected.acceptable_tools[0] for c in out)
    src_files = [Path(__file__), Path(__file__).parent / "generate.py"]
    meta = {
        "split": "test_v2",
        "model": MODEL,
        "temperature": TEMPERATURE,
        "reasoning_effort": "low",
        "seed": SEED,
        "n": len(out),
        "category_counts": dict(Counter(c.category for c in out)),
        "per_tool_any": {t: per_tool_any[t] for t in [*ALL_TOOLS, "__abstain__"]},
        "per_tool_first": {t: per_tool_first[t] for t in [*ALL_TOOLS, "__abstain__"]},
        "rounds_run": rnd,
        "calls": calls,
        "rejections": dict(sorted(rejects.items())),
        "thresholds": {
            "lexical_vs_existing_and_catalog": overlap.LEXICAL_THRESHOLD,
            "semantic_cosine": overlap.SEMANTIC_THRESHOLD,
            "lexical_within_v2": WITHIN_LEXICAL,
            "embedder": overlap.EMBED_MODEL,
        },
        "dedupe_references": {
            "existing_cases": len(existing),
            "catalog_units": len(units),
            "catalog_sha256": overlap.catalog_sha256(),
        },
        "prompts_sha256": hashlib.sha256("\n\x00".join(sorted(prompts)).encode()).hexdigest(),
        "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src_files},
        "mock_db_sha256": hashlib.sha256(MOCK_DB.read_bytes()).hexdigest(),
        "mock_db_satisfiability": {
            "cases_with_order": sum(bool(s["orders"]) for s in sat.values()),
            "first_tool_ok": sum(
                bool(s["orders"]) and all(r["first_ok"] for r in s["orders"]) for s in sat.values()
            ),
            "conflicts": sorted(k for k, s in sat.items() if s["conflict"]),
        },
        "total_cost_usd": round(total_cost, 4),
        "openrouter_total_usage_delta": round(after["total_usage"] - before["total_usage"], 4),
        "output_sha256_pre_audit": hashlib.sha256(OUT.read_bytes()).hexdigest(),
    }
    META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps({k: meta[k] for k in ("n", "category_counts", "rejections", "total_cost_usd")})
    )


if __name__ == "__main__":
    main()
