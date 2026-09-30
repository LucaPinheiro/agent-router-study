"""Cascade threshold calibration on the DEV split, from a rescored shadow run (projeto.md:
"Limiares ... vêm da calibração no split de desenvolvimento, nunca de chute").

A shadow row holds every strategy's decision for both stages, so any cascade can be replayed
offline for any `min_confidence` of its non-last steps. `simulate.simulate_rows` is the source
of truth for that replay (same `RoutingPipeline`, same shared scorer); it runs one asyncio
pipeline per row and stage, too slow for a full grid (E9: 50^2 skill x 50 tool combos). So:

1. `build_tables` enumerates, per row, every reachable stage outcome ("accepted at step k" or
   "no step accepted") and scores every (skill outcome, tool outcome) pair with the SAME rules
   as `simulate_rows` (shared scorer functions: `routing_scores`, `skill_can_be_correct`,
   `routing_failure`): error rows excluded, wrong skill = 0, tool stage not replayable when the
   simulated skill differs from the recorded one (`tool_unavailable`, joint counted 0), cost
   over covered rows only;
2. `grid_sums` picks each row's outcome for every threshold combination in numpy and sums
   per group (CV fold);
3. intention to treat (F2): an error row counts as WRONG and stays in the denominator, so a
   threshold cannot "win" by escalating hard cases to a step that failed on them;
   `ever_error` (rows that are an error row at SOME grid point) gives the error-free
   sensitivity analysis (`calibrate_cascades.py --error-free`);
4. `simulator_check` re-runs `simulate_rows` at chosen points and asserts both agree, so the
   fast path cannot drift from the simulator.

Two selection methods:
- (a) `select_budget`: max joint accuracy s.t. routing cost/case <= budget (ties: lower cost,
  then higher thresholds); `pareto_front` gives the whole accuracy-vs-cost front;
- (b) `precision_rule`: step by step, accept the cheap step at the LOWEST grid threshold whose
  precision on the cases it accepts (among those reaching it) is >= the next step's overall
  precision (on every fit case where the next step chose), with a minimum support.
`folds_of` + `crossval` report held-out accuracy/cost of each method (stratified k-fold over
case ids, fixed seed), so the choice is not judged on the cases it was fitted on.
"""

from __future__ import annotations

import itertools
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from routing_study.eval.scorers import routing_failure, routing_scores, skill_can_be_correct
from routing_study.eval.simulate import aggregate, simulate_rows
from routing_study.eval.stats import bootstrap_mean
from routing_study.routers.base import ABSTAIN
from routing_study.settings import Settings, StageConfig

Thresholds = tuple[float, ...]


def grid(lo: float = 0.50, hi: float = 0.99, step: float = 0.01) -> tuple[float, ...]:
    """Threshold grid, rounded to the step's decimals (0.50..0.99 by default)."""
    n = int(round((hi - lo) / step)) + 1
    digits = max(0, len(f"{step:.10f}".rstrip("0").split(".")[1]))
    return tuple(round(lo + i * step, digits) for i in range(n))


def steps_of(stage: StageConfig, mode: str) -> list[Any]:
    return stage.pipeline[:1] if mode == "single" else list(stage.pipeline)


def tuned_steps(stage: StageConfig, mode: str) -> list[str]:
    """Strategies whose min_confidence is calibrated: every step but the last."""
    return [s.strategy for s in steps_of(stage, mode)[:-1]]


def with_thresholds(settings: Settings, skill: Thresholds, tool: Thresholds) -> Settings:
    """Settings with the non-last steps' min_confidence replaced (the last step is kept)."""

    def patch(stage: StageConfig, ts: Thresholds) -> StageConfig:
        steps = [
            s.model_copy(update={"min_confidence": ts[i]}) if i < len(ts) else s
            for i, s in enumerate(stage.pipeline)
        ]
        return stage.model_copy(update={"pipeline": steps})

    r = settings.routing
    routing = r.model_copy(update={"skill": patch(r.skill, skill), "tool": patch(r.tool, tool)})
    return settings.model_copy(update={"routing": routing})


def configured(settings: Settings) -> tuple[Thresholds, Thresholds]:
    """The config's current thresholds (None -> 0.0: accept any choice)."""
    mode = settings.routing.mode
    return tuple(
        tuple(float(s.min_confidence or 0.0) for s in steps_of(stage, mode)[:-1])
        for stage in (settings.routing.skill, settings.routing.tool)
    )  # type: ignore[return-value]


# ---------------------------------------------------------------- per-row tables


@dataclass
class StageOutcomes:
    """One stage of one row: step decisions and the outcome of stopping at each step."""

    conf: list[float]  # per step (0.0 when no choice)
    has_choice: list[bool]
    last_min: float | None  # the last step's own (fixed) min_confidence
    choice: list[str]  # outcome k < m: step k's choice; outcome m: ABSTAIN
    cost: list[float]
    error: list[str | None]


def stage_outcomes(stage: StageConfig, shadow: dict[str, Any], mode: str) -> StageOutcomes | None:
    """None when a pipeline strategy was not recorded (as `simulate.replay_stage`)."""
    steps = steps_of(stage, mode)
    if not steps or any(s.strategy not in shadow for s in steps):
        return None
    ds = [shadow[s.strategy] for s in steps]
    costs = list(itertools.accumulate(float(d.get("cost_usd") or 0.0) for d in ds))
    return StageOutcomes(
        conf=[float(d.get("confidence") or 0.0) for d in ds],
        has_choice=[d.get("choice") is not None for d in ds],
        last_min=steps[-1].min_confidence,
        choice=[d.get("choice") or ABSTAIN for d in ds] + [ABSTAIN],
        cost=[*costs, costs[-1]],
        error=[None] * len(ds) + [routing_failure(ds, False)],
    )


@dataclass
class Tables:
    """Stacked per-row cell arrays, indexed [row, skill outcome, tool outcome]."""

    keys: list[tuple[str, int]]
    case_ids: list[str]
    categories: list[str]
    skill_conf: np.ndarray  # (N, m_s)
    skill_ok: np.ndarray  # (N, m_s) step has a choice
    skill_last: np.ndarray  # (N,) last step accepts
    tool_conf: np.ndarray  # (N, m_t)
    tool_ok: np.ndarray
    tool_last: np.ndarray
    err: np.ndarray  # (N, S, T) bool
    skill: np.ndarray  # skill_correct (0 on error)
    joint: np.ndarray  # joint_correct (0 on error / unavailable)
    known: np.ndarray  # joint is known (not error, not unavailable)
    unavail: np.ndarray
    cost: np.ndarray  # NaN when not covered
    step_correct: dict[str, np.ndarray]  # "skill"/"tool" -> (N, m) per-step correctness
    tool_rows: np.ndarray  # (N,) tool stage decisions are scorable (recorded skill ok)


def _last_accepts(o: StageOutcomes) -> bool:
    return o.has_choice[-1] and (o.last_min is None or o.conf[-1] >= o.last_min)


def _cell(
    r: dict[str, Any], sk: StageOutcomes, i: int, tl: StageOutcomes | None, j: int
) -> dict[str, Any]:
    """One (skill outcome i, tool outcome j) cell, with `simulate_rows`' rules."""
    exp = r["expected"]
    if sk.error[i]:
        return {"err": True}
    choice = sk.choice[i]
    recorded = (r["skill"].get("choice") or ABSTAIN) == choice
    tool = tl if recorded else None
    cost: float | None = sk.cost[i]
    if choice != ABSTAIN and skill_can_be_correct(choice, exp):
        if tool is None:
            ok = float(choice in exp["acceptable_skills"])
            return {"skill": ok, "unavail": True, "cost": None}
        if tool.error[j]:
            return {"err": True}
        cost = sk.cost[i] + tool.cost[j]
    elif choice != ABSTAIN:  # wrong skill: joint 0 whatever the tool
        cost = None if tool is None or tool.error[j] else sk.cost[i] + tool.cost[j]
    else:
        tool = None
    s = routing_scores(choice, tool.choice[j] if tool else None, exp)
    joint = s["joint_correct"] if skill_can_be_correct(choice, exp) else 0.0
    return {"skill": s["skill_correct"], "joint": joint, "cost": cost}


def build_tables(rows: Sequence[dict[str, Any]], settings: Settings) -> Tables:
    mode = settings.routing.mode
    ms = len(steps_of(settings.routing.skill, mode))
    mt = len(steps_of(settings.routing.tool, mode))
    n, S, T = len(rows), ms + 1, mt + 1
    err = np.zeros((n, S, T), bool)
    unavail = np.zeros((n, S, T), bool)
    skill = np.zeros((n, S, T))
    joint = np.zeros((n, S, T))
    known = np.zeros((n, S, T), bool)
    cost = np.full((n, S, T), np.nan)
    sconf, sok, slast = np.zeros((n, ms)), np.zeros((n, ms), bool), np.zeros(n, bool)
    tconf, tok, tlast = np.zeros((n, mt)), np.zeros((n, mt), bool), np.zeros(n, bool)
    step_correct = {"skill": np.zeros((n, ms)), "tool": np.zeros((n, mt))}
    tool_rows = np.zeros(n, bool)
    for x, r in enumerate(rows):
        shadow = (r.get("skill") or {}).get("shadow")
        if not shadow:
            err[x] = True
            continue
        sk = stage_outcomes(settings.routing.skill, shadow, mode)
        if sk is None:
            raise ValueError("skill pipeline strategy not recorded in the shadow run")
        tshadow = (r.get("tool") or {}).get("shadow")
        tl = stage_outcomes(settings.routing.tool, tshadow, mode) if tshadow else None
        sconf[x], sok[x], slast[x] = sk.conf, sk.has_choice, _last_accepts(sk)
        exp = r["expected"]
        step_correct["skill"][x] = [
            float(c != ABSTAIN and skill_can_be_correct(c, exp)) for c in sk.choice[:-1]
        ]
        rec_skill = r["skill"].get("choice") or ABSTAIN
        if tl is not None:
            tconf[x], tok[x], tlast[x] = tl.conf, tl.has_choice, _last_accepts(tl)
            if rec_skill != ABSTAIN and skill_can_be_correct(rec_skill, exp):
                tool_rows[x] = True
                step_correct["tool"][x] = [
                    routing_scores(rec_skill, c, exp)["joint_correct"] for c in tl.choice[:-1]
                ]
        for i, j in itertools.product(range(S), range(T)):
            c = _cell(r, sk, i, tl, j)
            if c.get("err"):
                err[x, i, j] = True
                continue
            skill[x, i, j] = c["skill"]
            unavail[x, i, j] = bool(c.get("unavail"))
            known[x, i, j] = not c.get("unavail")
            joint[x, i, j] = c.get("joint") or 0.0
            if c["cost"] is not None:
                cost[x, i, j] = c["cost"]
    return Tables(
        keys=[(r["case_id"], r["rep"]) for r in rows],
        case_ids=[r["case_id"] for r in rows],
        categories=[r.get("category") or "" for r in rows],
        skill_conf=sconf,
        skill_ok=sok,
        skill_last=slast,
        tool_conf=tconf,
        tool_ok=tok,
        tool_last=tlast,
        err=err,
        skill=skill,
        joint=joint,
        known=known,
        unavail=unavail,
        cost=cost,
        step_correct=step_correct,
        tool_rows=tool_rows,
    )


def outcome_index(
    conf: np.ndarray, ok: np.ndarray, last: np.ndarray, combos: np.ndarray
) -> np.ndarray:
    """(C, N) index of the first accepting step per combo and row (m = none accepted).
    `combos` is (C, m-1): the non-last steps' thresholds; the pipeline's `>=` rule."""
    n, m = conf.shape
    acc = np.empty((len(combos), n, m), bool)
    if m > 1:
        acc[:, :, :-1] = ok[None, :, :-1] & (conf[None, :, :-1] >= combos[:, None, :])
    acc[:, :, -1] = last[None, :]
    first = acc.argmax(axis=2)
    return np.where(acc.any(axis=2), first, m)


def ever_error(t: Tables, skill_combos: np.ndarray, tool_combos: np.ndarray) -> np.ndarray:
    """(N,) rows that are an error row for at least one threshold combination. Selecting on
    rows whose error status moves with the thresholds would let the optimizer drop failing
    cases from the denominator (e.g. escalate to a step that errored), so thresholds are
    compared on the rows error-free at EVERY grid point (as study_report's shared keys)."""
    ri = outcome_index(t.skill_conf, t.skill_ok, t.skill_last, skill_combos)  # (Cs, N)
    rj = outcome_index(t.tool_conf, t.tool_ok, t.tool_last, tool_combos)
    out = np.zeros(len(t.keys), bool)
    for x in range(len(t.keys)):
        i, j = np.unique(ri[:, x]), np.unique(rj[:, x])
        out[x] = bool(t.err[x][np.ix_(i, j)].any())
    return out


# ---------------------------------------------------------------- grid evaluation

FIELDS = ("n", "errors", "skill", "joint", "known", "unavail", "covered", "cost")


@dataclass
class GridSums:
    """Per (skill combo, tool combo, group) sums of the `aggregate` ingredients."""

    skill_combos: np.ndarray  # (Cs, m_s-1)
    tool_combos: np.ndarray  # (Ct, m_t-1)
    sums: dict[str, np.ndarray]  # field -> (Cs, Ct, G)

    def total(self, exclude: int | None = None) -> dict[str, np.ndarray]:
        """(Cs, Ct) sums over all groups, or all but group `exclude` (a CV train set)."""
        out = {}
        for k, v in self.sums.items():
            t = v.sum(axis=2)
            out[k] = t - v[:, :, exclude] if exclude is not None else t
        return out


def combos_of(values: Sequence[float], k: int) -> np.ndarray:
    """(len(values)**k, k) threshold combinations; one empty combo when k == 0."""
    if k == 0:
        return np.zeros((1, 0))
    return np.array(list(itertools.product(values, repeat=k)), float)


def grid_sums(
    t: Tables,
    skill_combos: np.ndarray,
    tool_combos: np.ndarray,
    groups: np.ndarray | None = None,
    *,
    max_cells: int = 4_000_000,
) -> GridSums:
    n = len(t.keys)
    g = np.zeros(n, int) if groups is None else np.asarray(groups)
    onehot = np.eye(int(g.max()) + 1 if n else 1)[g]  # (N, G)
    J = outcome_index(t.tool_conf, t.tool_ok, t.tool_last, tool_combos)  # (Ct, N)
    rows = np.arange(n)[None, None, :]
    cs, ct = len(skill_combos), len(tool_combos)
    sums = {k: np.zeros((cs, ct, onehot.shape[1])) for k in FIELDS}
    chunk = max(1, max_cells // max(1, ct * n))
    for a in range(0, cs, chunk):
        ic = outcome_index(t.skill_conf, t.skill_ok, t.skill_last, skill_combos[a : a + chunk])
        idx = (rows, ic[:, None, :], J[None, :, :])
        err = t.err[idx]
        cost = t.cost[idx]
        covered = ~err & ~np.isnan(cost)
        cells = {
            "n": ~err,
            "errors": err,
            "skill": t.skill[idx],
            "joint": t.joint[idx],
            "known": t.known[idx],
            "unavail": t.unavail[idx],
            "covered": covered,
            "cost": np.where(covered, cost, 0.0),
        }
        for k, v in cells.items():
            sums[k][a : a + chunk] = v.astype(float) @ onehot
    return GridSums(skill_combos, tool_combos, sums)


def metrics(s: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """ITT accuracy over every row (an error row is wrong), cost over covered rows (as
    `simulate.aggregate`); `n` counts every row, `n_ok` the error-free ones."""
    total = s["n"] + s["errors"]
    with np.errstate(invalid="ignore", divide="ignore"):
        return {
            "n": total,
            "n_ok": s["n"],
            "errors": s["errors"],
            "joint_acc": s["joint"] / total,
            "skill_acc": s["skill"] / total,
            "joint_acc_error_free": s["joint"] / s["n"],
            "joint_acc_covered": s["joint"] / s["known"],
            "cost": s["cost"] / s["covered"],
            "unavail": s["unavail"],
        }


def _pick(m: dict[str, np.ndarray], gs: GridSums, feasible: np.ndarray) -> tuple[int, int] | None:
    """Best feasible cell: max joint accuracy, then min cost, then highest thresholds."""
    cand = np.argwhere(feasible)
    if not len(cand):
        return None
    acc = np.round(m["joint_acc"][feasible], 12)
    cost = np.round(m["cost"][feasible], 15)
    thr = np.hstack([gs.skill_combos[cand[:, 0]], gs.tool_combos[cand[:, 1]]])
    keys = [-thr[:, c] for c in range(thr.shape[1] - 1, -1, -1)] + [cost, -acc]
    best = cand[np.lexsort(keys)[0]]
    return int(best[0]), int(best[1])


def select_budget(
    gs: GridSums, budget: float | None, exclude: int | None = None
) -> tuple[Thresholds, Thresholds] | None:
    """(a) max joint accuracy subject to routing cost/case <= budget (None: unconstrained)."""
    m = metrics(gs.total(exclude))
    feasible = (m["n_ok"] > 0) & ~np.isnan(m["joint_acc"])
    if budget is not None:
        feasible &= ~np.isnan(m["cost"]) & (m["cost"] <= budget + 1e-15)
    best = _pick(m, gs, feasible)
    if best is None:
        return None
    return tuple(gs.skill_combos[best[0]].tolist()), tuple(gs.tool_combos[best[1]].tolist())


def pareto_front(gs: GridSums) -> list[dict[str, Any]]:
    """Non-dominated (cost, joint accuracy) points; one representative per point (the
    `_pick` tie rule)."""
    m = metrics(gs.total())
    valid = (m["n_ok"] > 0) & ~np.isnan(m["cost"]) & ~np.isnan(m["joint_acc"])
    acc = np.round(m["joint_acc"][valid], 12)
    cost = np.round(m["cost"][valid], 15)
    order = np.lexsort((-acc, cost))
    out: list[dict[str, Any]] = []
    best = -1.0
    for o in order:
        if acc[o] <= best:
            continue
        best = float(acc[o])
        same = (
            valid & (np.round(m["joint_acc"], 12) == acc[o]) & (np.round(m["cost"], 15) == cost[o])
        )
        a, b = _pick(m, gs, same)  # type: ignore[misc]
        out.append(
            {
                "skill": tuple(gs.skill_combos[a].tolist()),
                "tool": tuple(gs.tool_combos[b].tolist()),
                "joint_acc": float(m["joint_acc"][a, b]),
                "joint_acc_covered": float(m["joint_acc_covered"][a, b]),
                "skill_acc": float(m["skill_acc"][a, b]),
                "cost": float(m["cost"][a, b]),
                "n": int(m["n"][a, b]),
                "errors": int(m["errors"][a, b]),
                "unavail": int(m["unavail"][a, b]),
            }
        )
    return out


# ---------------------------------------------------------------- (b) precision rule


@dataclass
class RuleStep:
    stage: str
    strategy: str
    target: float | None  # next step's overall precision
    threshold: float | None  # None: no grid value meets the target (step never trusted)
    precision: float | None  # of the accepted cases at `threshold`
    accepted: int


def precision_rule(
    t: Tables,
    stage: str,
    strategies: Sequence[str],
    thresholds: Sequence[float],
    mask: np.ndarray | None = None,
    *,
    min_support: int = 5,
) -> list[RuleStep]:
    """(b) step by step: the lowest grid threshold whose precision on the cases the step
    accepts (among those reaching it, i.e. not taken by an earlier step) is >= the next
    step's precision over every case where it chose. Rows: non-error for the skill stage;
    for the tool stage, rows whose recorded skill can be correct (tool decisions scorable)."""
    conf = t.skill_conf if stage == "skill" else t.tool_conf
    ok = t.skill_ok if stage == "skill" else t.tool_ok
    correct = t.step_correct[stage]
    base = np.ones(len(t.keys), bool) if mask is None else mask.copy()
    base &= ~t.err.all(axis=(1, 2))
    if stage == "tool":
        base &= t.tool_rows
    reaching = base.copy()
    out = []
    for k, name in enumerate(strategies):
        nxt = base & ok[:, k + 1]
        target = float(correct[nxt, k + 1].mean()) if nxt.any() else None
        chosen: tuple[float | None, float | None, int] = (None, None, 0)
        if target is not None:
            for th in thresholds:
                acc = reaching & ok[:, k] & (conf[:, k] >= th)
                if acc.sum() >= min_support and correct[acc, k].mean() >= target - 1e-12:
                    chosen = (th, float(correct[acc, k].mean()), int(acc.sum()))
                    break
        out.append(RuleStep(stage, name, target, *chosen))
        th = chosen[0]
        if th is not None:
            reaching &= ~(ok[:, k] & (conf[:, k] >= th))
    return out


def rule_thresholds(steps: Sequence[RuleStep], never: float = 1.01) -> Thresholds:
    """Thresholds of a rule result; a step that never met its target gets `never` (above
    any confidence, i.e. always pass on). Configs cap min_confidence at 1.0: report it."""
    return tuple(s.threshold if s.threshold is not None else never for s in steps)


# ---------------------------------------------------------------- CV + held-out estimate


def folds_of(case_categories: dict[str, str], k: int, seed: int) -> dict[str, int]:
    """case id -> fold, stratified by category, seeded (as scripts/analysis/tune_router.py)."""
    rng = random.Random(seed)
    by_cat: dict[str, list[str]] = defaultdict(list)
    for cid, cat in case_categories.items():
        by_cat[cat].append(cid)
    out: dict[str, int] = {}
    offset = 0
    for cat in sorted(by_cat):
        ids = sorted(by_cat[cat])
        rng.shuffle(ids)
        for i, cid in enumerate(ids):
            out[cid] = (offset + i) % k
        offset += len(ids)
    return out


def row_values(t: Tables, skill: Thresholds, tool: Thresholds) -> list[dict[str, Any]]:
    """Per-row result of one threshold choice (for held-out pooling and bootstrap)."""
    i = outcome_index(t.skill_conf, t.skill_ok, t.skill_last, np.array([skill], float))[0]
    j = outcome_index(t.tool_conf, t.tool_ok, t.tool_last, np.array([tool], float))[0]
    out = []
    for x in range(len(t.keys)):
        a, b = i[x], j[x]
        cost = t.cost[x, a, b]
        out.append(
            {
                "case_id": t.case_ids[x],
                "error": bool(t.err[x, a, b]),
                "joint": float(t.joint[x, a, b]),
                "cost": None if np.isnan(cost) else float(cost),
            }
        )
    return out


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """ITT joint accuracy (an error row is wrong) and cost/case (covered rows), 95%
    cluster-bootstrap CIs over case ids (`stats.bootstrap_mean`)."""
    joint: dict[str, list[float]] = defaultdict(list)
    cost: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        joint[r["case_id"]].append(0.0 if r["error"] else r["joint"])
        if not r["error"] and r["cost"] is not None:
            cost[r["case_id"]].append(r["cost"])
    return {
        "n": sum(len(v) for v in joint.values()),
        "errors": sum(1 for r in rows if r["error"]),
        "joint_ci": bootstrap_mean(joint),
        "cost_ci": bootstrap_mean(cost),
    }


Selector = Callable[[int | None], tuple[Thresholds, Thresholds] | None]


def crossval(
    t: Tables, fold: dict[str, int], select: Selector
) -> tuple[list[dict[str, Any]], list[tuple[Thresholds, Thresholds] | None]]:
    """Pooled held-out rows of `select(exclude=f)` fitted on the other folds, and the picks."""
    held: list[dict[str, Any]] = []
    picks = []
    k = max(fold.values()) + 1 if fold else 0
    for f in range(k):
        pick = select(f)
        picks.append(pick)
        if pick is None:
            continue
        vals = row_values(t, *pick)
        held += [v for v in vals if fold[v["case_id"]] == f]
    return held, picks


# ---------------------------------------------------------------- simulator cross-check


def simulator_check(
    rows: list[dict[str, Any]],
    settings: Settings,
    t: Tables,
    skill: Thresholds,
    tool: Thresholds,
) -> dict[str, Any]:
    """`simulate.aggregate(simulate_rows(...))` at one choice vs the fast path; raises
    AssertionError on any mismatch."""
    sim = aggregate(simulate_rows(rows, with_thresholds(settings, skill, tool)))
    gs = grid_sums(t, np.array([skill], float), np.array([tool], float))
    m = {k: v[0, 0] for k, v in metrics(gs.total()).items()}
    fast = {
        "n": int(m["n"]),
        "errors": int(m["errors"]),
        "skill_acc": None if np.isnan(m["skill_acc"]) else float(m["skill_acc"]),
        "joint_acc": None if np.isnan(m["joint_acc"]) else float(m["joint_acc"]),
        "tool_unavailable": int(m["unavail"]),
        "routing_cost_case": None if np.isnan(m["cost"]) else float(m["cost"]),
    }
    for k, v in fast.items():
        s = sim[k]
        same = (s is None and v is None) or (
            s is not None and v is not None and abs(float(s) - float(v)) <= 1e-9 * max(1, abs(s))
        )
        if not same:
            raise AssertionError(f"fast evaluator != simulate_rows on {k}: {v} vs {s}")
    return fast
