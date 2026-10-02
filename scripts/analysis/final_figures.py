# ruff: noqa: E501  (report prose and table rows)
"""Figures of the final test-v2 analysis (estudos/figuras/final-*.png), from estimation.json.

One light chart surface (#fcfcfb) with dark ink so each PNG reads the same embedded in a light
or a dark page; 200 dpi (2x). Colour = router family (dataviz reference palette, validated
all-pairs for these four slots), always doubled by marker shape and direct labels.
"""

from __future__ import annotations

from typing import Any

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from final_common import (  # noqa: E402
    CATEGORIES,
    FAMILY_COLOR,
    FAMILY_MARKER,
    FIG,
    GRID,
    SURFACE,
    TEXT,
    TEXT2,
)

DPI = 200
FREE_X = 0.02  # where $0 routers sit on the log cost axis
SERIES4 = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": TEXT2,
        "axes.labelcolor": TEXT,
        "text.color": TEXT,
        "xtick.color": TEXT2,
        "ytick.color": TEXT2,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "legend.frameon": False,
    }
)


def _save(fig: Any, name: str, out: list[str]) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    out.append(str(path))


def _labels(ax: Any, pts: list[tuple[float, float, str]]) -> None:
    """Direct labels with greedy collision avoidance (candidate offsets in points)."""
    fig = ax.figure
    fig.canvas.draw()
    k = fig.dpi / 72.0
    placed: list[tuple[float, float, float, float]] = []
    cands = [(6, 3), (14, -10), (14, 12), (-14, 4), (14, -22), (14, 24), (-14, -10), (-14, 14)]
    for x, y, text in sorted(pts, key=lambda p: -p[1]):
        px, py = ax.transData.transform((x, y))
        w, h = 5.2 * len(text) * k, 9 * k
        for dx, dy in cands:
            x0 = px + dx * k - (w if dx < 0 else 0)
            y0 = py + dy * k
            box = (x0, y0, x0 + w, y0 + h)
            if not any(
                box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed
            ):
                break
        placed.append(box)
        leader = (
            {"arrowstyle": "-", "color": TEXT2, "lw": 0.6, "shrinkA": 0, "shrinkB": 3}
            if (dx, dy) != (6, 3)
            else None
        )
        ax.annotate(
            text,
            (x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=7.5,
            color=TEXT,
            ha="right" if dx < 0 else "left",
            va="center" if leader else "baseline",
            arrowprops=leader,
        )


def _family_legend(ax: Any, families: set[str]) -> None:
    names = {
        "lexical": "lexical (local)",
        "local-semantic": "semantic / local model",
        "api-llm": "API LLM",
        "cascade": "cascade",
        "native": "native",
    }
    handles = [
        plt.Line2D(
            [],
            [],
            color=FAMILY_COLOR[f],
            marker=FAMILY_MARKER[f],
            linestyle="none",
            markersize=7,
            label=names[f],
        )
        for f in ("lexical", "local-semantic", "api-llm", "cascade", "native")
        if f in families
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8)


def pareto(est: dict[str, Any], out: list[str]) -> None:
    st = est["strategies"]
    fig, ax = plt.subplots(figsize=(8, 5.2))
    fams = set()
    pts: list[tuple[float, float, str]] = []
    for k, s in st.items():
        j, c = s["joint"], s["cost_observed_per_case"]
        x = 1000 * c["point"]
        xs = FREE_X if x <= 0 else x
        xerr = (
            None if x <= 0 else [[1000 * (c["point"] - c["lo"])], [1000 * (c["hi"] - c["point"])]]
        )
        fams.add(s["family"])
        ax.errorbar(
            xs,
            100 * j["point"],
            yerr=[[100 * (j["point"] - j["lo"])], [100 * (j["hi"] - j["point"])]],
            xerr=xerr,
            fmt=FAMILY_MARKER[s["family"]],
            color=FAMILY_COLOR[s["family"]],
            ms=7,
            mec=SURFACE,
            mew=1.2,
            elinewidth=1,
            capsize=0,
            alpha=0.6 if s["status"] == "exploratory" else 1.0,
        )
        pts.append((xs, 100 * j["point"], k))
    sh = (est.get("cascades") or {}).get("shadow") or {}
    if "E9" in sh and sh["E9"].get("test_insample_front"):
        f = sh["E9"]["test_insample_front"]
        ax.plot(
            [p["cost_1k"] for p in f],
            [100 * p["joint"] for p in f],
            color=FAMILY_COLOR["cascade"],
            alpha=0.35,
            lw=1.2,
            ls="--",
            label="E9 thresholds fitted on test shadow (exploratory, optimistic, lower-bound replay)",
        )
        ax.legend(loc="upper left", fontsize=7)
    ax.set_xscale("log")
    _labels(ax, pts)
    ax.axvline(FREE_X * 1.6, color=GRID, lw=1)
    ax.text(
        FREE_X,
        ax.get_ylim()[0] + 1,
        "$0\n(local)",
        ha="center",
        va="bottom",
        fontsize=7,
        color=TEXT2,
    )
    ax.set_xlabel("routing cost, US$ per 1 000 cases (observed regime, log scale; 95% CI)")
    ax.set_ylabel("joint accuracy % (ITT, 95% CI)")
    ax.set_title("Accuracy vs routing cost on test-v2")
    leg = ax.get_legend()
    _family_legend(ax, fams)
    if leg is not None:
        ax.add_artist(leg)
    _save(fig, "final-pareto-accuracy-cost.png", out)


def acc_latency(est: dict[str, Any], out: list[str]) -> None:
    st, lat = est["strategies"], est["latency"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), gridspec_kw={"width_ratios": [1.25, 1]})
    fams: set[str] = set()
    for panel, ax in enumerate(axes):
        pts: list[tuple[float, float, str]] = []
        for k, s in st.items():
            if not s.get("lat") or s["lat"] not in lat:
                continue
            p95 = lat[s["lat"]]["warm"]["95"]
            j = s["joint"]
            x = max(p95["point"], 0.05)
            if panel == 1 and x < 2000:
                continue
            fams.add(s["family"])
            ax.errorbar(
                x,
                100 * j["point"],
                yerr=[[100 * (j["point"] - j["lo"])], [100 * (j["hi"] - j["point"])]],
                xerr=[[max(x - max(p95["lo"], 0.05), 0)], [max(p95["hi"] - x, 0)]],
                fmt=FAMILY_MARKER[s["family"]],
                color=FAMILY_COLOR[s["family"]],
                ms=7,
                mec=SURFACE,
                mew=1.2,
                elinewidth=1,
            )
            pts.append((x, 100 * j["point"], k))
        ax.set_xscale("log")
        if panel == 1:
            ax.set_xlim(2000, 20000)
            ticks = [2000, 3000, 5000, 7000, 10000, 15000, 20000]
            ax.set_xticks(ticks, [f"{t / 1000:g} s" for t in ticks])
            ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        _labels(ax, pts)
        lo, hi = ax.get_xlim()
        for slo in (50, 500, 2000, 10000):
            if lo <= slo <= hi:
                ax.axvline(slo, color=TEXT2, lw=0.8, ls=":")
                ax.text(slo, ax.get_ylim()[1], f" {slo:g} ms", fontsize=7, color=TEXT2, va="top")
        ax.set_xlabel("warm p95 routing latency, ms (log; 95% CI)")
    axes[0].set_ylabel("joint accuracy % on test-v2 (ITT, 95% CI)")
    axes[0].set_title("Accuracy vs p95 latency (lat-* benchmark)")
    axes[1].set_title("zoom: routers with p95 >= 2 s")
    _family_legend(axes[0], fams)
    _save(fig, "final-accuracy-latency-p95.png", out)


def reliability(est: dict[str, Any], out: list[str]) -> None:
    keys = [k for k in ("E5", "E6", "E6b", "E4", "E11", "E9") if k in est["calibration"]]
    if not keys:
        return
    fig, axes = plt.subplots(2, len(keys), figsize=(2.6 * len(keys), 5.4), sharex=True, sharey=True)
    axes = np.atleast_2d(axes)
    for c, k in enumerate(keys):
        for r, lv in enumerate(("skill", "tool")):
            ax = axes[r, c]
            ax.plot([0, 1], [0, 1], color=TEXT2, lw=0.8, ls=":")
            cal = est["calibration"][k][lv]
            for name, color, mk in (("raw", SERIES4[0], "o"), ("dev_map", SERIES4[1], "s")):
                d = cal.get(name)
                if not d:
                    continue
                xs = [b[1] for b in d["bins"]]
                ys = [b[2] for b in d["bins"]]
                ax.plot(
                    xs,
                    ys,
                    marker=mk,
                    color=color,
                    lw=1.5,
                    ms=4,
                    label=f"{'raw' if name == 'raw' else 'dev-calibrated'} ECE {d['ece']:.3f}",
                )
            ax.legend(fontsize=6.5, loc="lower right")
            if r == 0:
                ax.set_title(est["strategies"][k]["label"].split(" (")[0], fontsize=9)
            if c == 0:
                ax.set_ylabel(f"{lv}: observed accuracy")
            if r == 1:
                ax.set_xlabel("mean confidence (bin)")
    fig.suptitle(
        "Reliability on test-v2 (10 equal-mass bins); dev-calibrated = deployed map, or the dev map applied post hoc",
        fontsize=9,
    )
    _save(fig, "final-reliability.png", out)


def risk_cov(est: dict[str, Any], out: list[str]) -> None:
    keys = [
        k
        for k in ("E1", "E3", "E10", "E11", "E6b", "E4", "E5", "E6", "E7", "E9")
        if k in est["calibration"]
    ]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    st = est["strategies"]
    styles = ["-", "--", ":", "-."]
    seen: dict[str, int] = {}
    for k in keys:
        rc = est["calibration"][k]["risk"]
        fam = st[k]["family"]
        i = seen.get(fam, 0)
        seen[fam] = i + 1
        ax.step(
            [100 * c for c in rc["coverage"]],
            [100 * r for r in rc["risk"]],
            where="post",
            color=FAMILY_COLOR[fam],
            ls=styles[i % 4],
            lw=1.6,
            label=f"{k} AURC {rc['aurc']:.3f}",
        )
    ax.axhline(5, color=TEXT2, lw=0.8, ls=":")
    ax.text(1, 5.5, "5% risk", fontsize=7, color=TEXT2)
    ax.set_xlabel("coverage % (cases answered, most confident first)")
    ax.set_ylabel("risk % (joint error among answered; ITT)")
    ax.set_title("Risk-coverage on test-v2")
    ax.legend(fontsize=7, ncol=2, loc="upper left")
    _save(fig, "final-risk-coverage.png", out)


def heatmap(est: dict[str, Any], out: list[str]) -> None:
    cat = est["breakdowns"]["category"]
    keys = list(cat)
    m = np.array(
        [[100 * (cat[k][c]["point"] if cat[k][c] else np.nan) for c in CATEGORIES] for k in keys]
    )
    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(keys) + 1.4))
    im = ax.imshow(m, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(len(CATEGORIES)), CATEGORIES)
    ax.set_yticks(range(len(keys)), [est["strategies"][k]["label"] for k in keys])
    for i in range(len(keys)):
        for j in range(len(CATEGORIES)):
            v = m[i, j]
            ax.text(
                j,
                i,
                f"{v:.0f}",
                ha="center",
                va="center",
                fontsize=7.5,
                color="#ffffff" if v >= 60 else TEXT,
            )
    fig.colorbar(im, ax=ax, label="joint % (ITT)")
    ax.set_title("Joint accuracy by category (descriptive)")
    _save(fig, "final-category-heatmap.png", out)


def e2e_bars(est: dict[str, Any], out: list[str]) -> None:
    e = {k: v for k, v in est["e2e"].items() if k != "executor_variance"}
    if not e:
        return
    keys = list(e)
    parts = (
        ("first_call_success", "first call"),
        ("clarification_credited", "clarification credited"),
        ("recovered_credited", "recovered"),
    )
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    left = np.zeros(len(keys))
    for (s, lab), color in zip(parts, SERIES4, strict=False):
        vals = np.array([100 * e[k][s]["point"] for k in keys])
        ax.barh(
            range(len(keys)),
            vals,
            left=left,
            color=color,
            label=lab,
            edgecolor=SURFACE,
            linewidth=2,
            height=0.6,
        )
        left += vals
    for i, k in enumerate(keys):
        ci = e[k]["e2e_success"]
        ax.errorbar(
            100 * ci["point"],
            i,
            xerr=[[100 * (ci["point"] - ci["lo"])], [100 * (ci["hi"] - ci["point"])]],
            color=TEXT,
            capsize=3,
            lw=1,
        )
        ax.text(
            100 * ci["hi"] + 1,
            i,
            f"{100 * ci['point']:.1f}%  (US$ {1000 * e[k]['cost_turn']['point']:.1f}/1k turns)",
            va="center",
            fontsize=7.5,
        )
    ax.set_yticks(range(len(keys)), [e[k]["label"] for k in keys])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("e2e_success % (ITT; bars = disjoint parts, whisker = 95% CI of the total)")
    ax.set_title("End-to-end success decomposition (executor Sonnet 5)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=7.5)
    _save(fig, "final-e2e-decomposition.png", out)


def cascade_cov(est: dict[str, Any], out: list[str]) -> None:
    cov = est["cascades"]["coverage"]
    if not cov:
        return
    order = ["regex", "hybrid", "jev", "llm", "(abstained)", "(error)"]
    colors = {
        "regex": "#2a78d6",
        "hybrid": "#1baf7a",
        "jev": "#eb6834",
        "llm": "#4a3aa7",
        "(abstained)": "#a3a29c",
        "(error)": "#e34948",
    }
    rows = [(k, lv) for k in cov for lv in ("skill", "tool")]
    fig, ax = plt.subplots(figsize=(7.5, 0.5 * len(rows) + 1.2))
    for i, (k, lv) in enumerate(rows):
        left = 0.0
        for step in order:
            d = cov[k].get(f"{lv}|{step}")
            if not d:
                continue
            w = 100 * d["share"]
            ax.barh(i, w, left=left, color=colors[step], edgecolor=SURFACE, linewidth=2, height=0.6)
            if w >= 6:
                acc = "" if d["acc"] is None else f" {100 * d['acc']:.0f}%"
                ax.text(
                    left + w / 2,
                    i,
                    f"{w:.0f}%{acc}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="#ffffff",
                )
            left += w
    ax.set_yticks(range(len(rows)), [f"{k} {lv}" for k, lv in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of rows resolved at each step (label: share, accuracy there)")
    present = [st for st in order if any(f"{lv}|{st}" in cov[k] for k, lv in rows)]
    names = {
        "regex": "regex",
        "hybrid": "hybrid",
        "jev": "Jev",
        "llm": "Sonnet (llm)",
        "(abstained)": "abstained",
        "(error)": "error row",
    }
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[st]) for st in present]
    ax.grid(False)
    ax.legend(
        handles,
        [names[st] for st in present],
        ncol=len(present),
        fontsize=7.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
    )
    ax.set_title("Cascade coverage per step (real test-v2 runs)")
    ax.grid(False, axis="y")
    _save(fig, "final-cascade-coverage.png", out)


def latency_dist(est: dict[str, Any], out: list[str]) -> None:
    lat = est["latency"]
    if not lat:
        return
    keys = list(lat)
    fig, ax = plt.subplots(figsize=(8, 4.6))
    data = [np.maximum(np.asarray(lat[k]["warm_values"]), 0.01) for k in keys]
    bp = ax.boxplot(
        data,
        vert=True,
        whis=(5, 95),
        showfliers=True,
        patch_artist=True,
        widths=0.55,
        flierprops={"marker": ".", "markersize": 3, "markeredgecolor": TEXT2},
    )
    for patch, k in zip(bp["boxes"], keys, strict=True):
        patch.set_facecolor(
            FAMILY_COLOR["local-semantic"] if lat[k]["local"] else FAMILY_COLOR["api-llm"]
        )
        patch.set_edgecolor(TEXT)
    for med in bp["medians"]:
        med.set_color(TEXT)
    for i, k in enumerate(keys, start=1):
        cold = lat[k]["cold_ms"]
        ax.scatter(
            [i + 0.32] * len(cold),
            np.maximum(cold, 0.01),
            marker="x",
            color=TEXT,
            s=14,
            lw=1,
            zorder=3,
        )
    ax.set_yscale("log")
    ax.set_xticks(range(1, len(keys) + 1), keys, rotation=30)
    ax.set_ylabel("routing latency per case, ms (log)")
    ax.set_title("Latency distribution: warm (box: IQR, whiskers p5-p95) and cold first case (x)")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=FAMILY_COLOR["local-semantic"]),
        plt.Rectangle((0, 0), 1, 1, color=FAMILY_COLOR["api-llm"]),
        plt.Line2D([], [], marker="x", color=TEXT, linestyle="none"),
    ]
    ax.legend(
        handles, ["local", "API", "cold first case of a block"], fontsize=7.5, loc="upper left"
    )
    _save(fig, "final-latency-distribution.png", out)


def jev_mix(est: dict[str, Any], out: list[str]) -> None:
    j = est["jev"].get("E4")
    if not j:
        return
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    for i, lv in enumerate(("skill", "tool")):
        items = sorted(
            ((k.split("|", 1)[1], v) for k, v in j.items() if k.startswith(lv + "|")),
            key=lambda kv: -kv[1]["calls"],
        )
        top, other = items[:3], items[3:]
        if other:
            calls = sum(v["calls"] for _, v in other)
            n = sum(v["resolved_n"] for _, v in other)
            acc = sum((v["acc"] or 0) * v["resolved_n"] for _, v in other) / n if n else None
            top.append(("other", {"calls": calls, "resolved_n": n, "acc": acc}))
        tot = sum(v["calls"] for _, v in top)
        left = 0.0
        for (m, v), color in zip(top, SERIES4, strict=False):
            w = 100 * v["calls"] / tot
            ax.barh(
                i,
                w,
                left=left,
                color=color,
                edgecolor=SURFACE,
                linewidth=2,
                height=0.6,
                label=m if i == 0 else None,
            )
            if w >= 15:
                ax.text(
                    left + w / 2,
                    i,
                    f"{m.split('/')[-1]}\n{w:.0f}% · acc {100 * (v['acc'] or 0):.0f}%",
                    ha="center",
                    va="center",
                    fontsize=6.5,
                    color="#ffffff",
                )
            left += w
    ax.set_yticks([0, 1], ["skill calls", "tool calls"])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.grid(False)
    ax.set_xlabel(
        "share of Jev calls by served model (E4 Jev, 3 reps; in-bar: share, accuracy over resolved decisions; exploratory; full table in estimation.md H)"
    )
    ax.legend(ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.35))
    ax.set_title("Jev served-model mix")
    ax.grid(False, axis="y")
    _save(fig, "final-jev-served-mix.png", out)


def run_figures(est: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for fn in (
        pareto,
        acc_latency,
        reliability,
        risk_cov,
        heatmap,
        e2e_bars,
        cascade_cov,
        latency_dist,
        jev_mix,
    ):
        fn(est, out)
    return out
