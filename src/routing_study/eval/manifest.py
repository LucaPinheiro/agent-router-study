"""Pre-registered run manifest (F11, methodology B6 / M10): `study run-manifest <yaml>`.

Each manifest entry is one run: name, config, prompt track, mode (+ routing mode), reps,
split, case filter (all, or a stratified seeded subset, or an id list) and priority. The runner
executes the entries in priority order and follows these rules:

- **Version guard.** The config's LLM / Jev strategies must be on the entry's `prompt_track`.
  When the entry freezes `config_hash` / `prompt_hash` (pre-registration), the current code
  must reproduce them. Rows already written must carry the same hashes. Any mismatch stops
  the entry: rows of different versions never mix.
- **Budget pre-check.** It projects the MEASURED cost per turn (`estimate.measured_cost`, from
  earlier results of the same config and mode) over the missing turns and checks it against
  the ledger caps. The a-priori upper bound is used only when nothing was measured.
- **Resume.** Only the missing (case, rep) keys are appended to the existing results file. A
  crashed run's paid `.partial` is continued, never deleted.
- **Completion.** A run is complete when every key is present and its error rate is <=
  `error_budget` (2%). Error rows stay in the file and count as wrong (ITT).
- **Retry rule (pre-registered).** When a run is above the error budget, its error rows (infra
  failures) are moved to `<name>.retry<k>.errors.jsonl` (kept for audit) and re-run. This is
  done at most `max_infra_retries` (2) times. A run still above budget after that is FLAGGED:
  the rule says fix the infrastructure and redo it from scratch (by hand, after review). It is
  never re-run for any other reason.

Every run is rescored into `results/rescored/` after it executes. Every decision is appended to
`results/manifest-<manifest stem>.log`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from routing_study.eval.runner import SAMPLE_SEED, Case, config_hash, load_cases, run_prompt_hash
from routing_study.eval.stats import Contrast

RESCORED = Path("results/rescored")


class CaseFilter(BaseModel):
    """All cases of the split, or `limit` stratified by category (seeded), or the ids listed
    in `ids_file` (one per line)."""

    model_config = ConfigDict(extra="forbid")
    limit: int | None = Field(default=None, ge=1)
    seed: int = SAMPLE_SEED
    ids_file: Path | None = None


class ManifestRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    config: Path
    prompt_track: Literal["canonical", "tuned", "none"] = "none"
    mode: Literal["e2e", "routing-only"]
    routing_mode: Literal["single", "cascade", "shadow"] | None = None
    reps: int = Field(default=1, ge=1)
    split: str | None = None  # default: the manifest's split
    cases: CaseFilter = Field(default_factory=CaseFilter)
    priority: int = 100
    concurrency: int = Field(default=4, ge=1)
    config_hash: str | None = None  # frozen at pre-registration (asserted)
    prompt_hash: str | None = None
    purpose: str = ""


class ContrastSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: str
    reference: str
    family: str = "exploratory"
    kind: Literal["two_sided", "greater", "non_inferiority", "equivalence"] = "two_sided"
    margin: float = 0.03

    def contrast(self) -> Contrast:
        return Contrast(self.run, self.reference, self.family, self.kind, self.margin)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    split: str
    results_dir: Path = Path("results")
    error_budget: float = 0.02
    max_infra_retries: int = 2
    runs: list[ManifestRun]
    contrasts: list[ContrastSpec] = Field(default_factory=list)

    def ordered(self, only: list[str] | None = None) -> list[ManifestRun]:
        runs = [r for r in self.runs if not only or r.name in only]
        if only and (unknown := set(only) - {r.name for r in runs}):
            raise ValueError(f"unknown run(s) {sorted(unknown)}")
        return sorted(runs, key=lambda r: (r.priority, self.runs.index(r)))

    def split_of(self, run: ManifestRun) -> str:
        return run.split or self.split


def load_manifest(path: Path) -> Manifest:
    m = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    names = [r.name for r in m.runs]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: duplicate run names")
    return m


# ---------------------------------------------------------------- per-run state


def select_cases(run: ManifestRun, split: str, data_dir: Path = Path("data")) -> list[Case]:
    from routing_study.eval.runner import stratified_sample

    cases = load_cases(split, None, data_dir=data_dir)
    if run.cases.ids_file is not None:
        ids = {x.strip() for x in run.cases.ids_file.read_text("utf-8").splitlines() if x.strip()}
        missing = ids - {c.id for c in cases}
        if missing:
            raise ValueError(f"{run.name}: ids not in split {split}: {sorted(missing)[:5]}")
        cases = [c for c in cases if c.id in ids]
    if run.cases.limit is not None and run.cases.limit < len(cases):
        rows = [{"id": c.id, "category": c.category} for c in cases]
        keep = {r["id"] for r in stratified_sample(rows, run.cases.limit, run.cases.seed)}
        cases = [c for c in cases if c.id in keep]
    return cases


def read_rows(results_dir: Path, name: str) -> list[dict[str, Any]]:
    """Rows of `<name>.jsonl` (or its crashed `.partial`), read-only (a torn last line is
    ignored here; the resume repairs it)."""
    out = results_dir / f"{name}.jsonl"
    path = out if out.exists() else out.with_name(out.name + ".partial")
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def retries_used(results_dir: Path, name: str) -> int:
    return len(list(results_dir.glob(f"{name}.retry*.errors.jsonl")))


def status(
    manifest: Manifest, run: ManifestRun, cases: list[Case], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    wanted = {(c.id, rep) for c in cases for rep in range(1, run.reps + 1)}
    present = {(r["case_id"], int(r["rep"])) for r in rows}
    errors = sum(1 for r in rows if r.get("error") and (r["case_id"], int(r["rep"])) in wanted)
    missing = wanted - present
    rate = errors / len(wanted) if wanted else 0.0
    return {
        "wanted": len(wanted),
        "present": len(present & wanted),
        "missing": len(missing),
        "extra": len(present - wanted),
        "errors": errors,
        "error_rate": rate,
        "retries_used": retries_used(manifest.results_dir, run.name),
        "complete": not missing and rate <= manifest.error_budget + 1e-12,
        "row_hashes": {
            k: sorted({str(r[k]) for r in rows if r.get(k)}) for k in ("config_hash", "prompt_hash")
        },
    }


def quarantine_errors(results_dir: Path, name: str) -> Path:
    """Move the error rows of `<name>.jsonl` to `<name>.retry<k>.errors.jsonl` (kept for
    audit) and rewrite the results file without them (atomic replace)."""
    out = results_dir / f"{name}.jsonl"
    rows = read_rows(results_dir, name)
    k = retries_used(results_dir, name) + 1
    dest = results_dir / f"{name}.retry{k}.errors.jsonl"
    dest.write_text("".join(json.dumps(r) + "\n" for r in rows if r.get("error")), "utf-8")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows if not r.get("error")),
        "utf-8",
    )
    tmp.replace(out)
    return dest


# ---------------------------------------------------------------- version / budget checks


def load_run_settings(run: ManifestRun) -> Any:
    from routing_study.settings import load_settings

    settings = load_settings(run.config)
    if run.routing_mode:
        settings.routing.mode = run.routing_mode
    return settings


def run_roles(settings: Any, run: ManifestRun, split: str) -> set[str]:
    from routing_study.eval.runner import Runner

    return Runner(settings, split=split, mode=run.mode, run_name=run.name).model_roles()


def version_problems(run: ManifestRun, settings: Any, split: str) -> list[str]:
    """Why this entry must not run with the current code/config (empty = fine)."""
    from routing_study.eval.runner import prompt_tracks

    out = []
    tracks = set(prompt_tracks(settings, run_roles(settings, run, split)).values())
    if run.prompt_track == "none" and tracks:
        out.append(f"config calls LLM/Jev routers on track(s) {sorted(tracks)}: set prompt_track")
    elif run.prompt_track != "none" and tracks != {run.prompt_track}:
        out.append(f"prompt_track {run.prompt_track} but the config's routers are {sorted(tracks)}")
    if run.config_hash and config_hash(settings) != run.config_hash:
        out.append(f"config_hash {config_hash(settings)} != frozen {run.config_hash}")
    if run.prompt_hash and run_prompt_hash() != run.prompt_hash:
        out.append(f"prompt_hash {run_prompt_hash()} != frozen {run.prompt_hash}")
    return out


def row_version_problems(st: dict[str, Any], settings: Any) -> list[str]:
    current = {"config_hash": config_hash(settings), "prompt_hash": run_prompt_hash()}
    return [
        f"existing rows have {k}={v}, current {current[k]}"
        for k, v in st["row_hashes"].items()
        if v and v != [current[k]]
    ]


async def turn_cost(settings: Any, mode: str, roles: set[str]) -> tuple[dict[str, float], str]:
    """USD per turn by provider: measured (earlier rows of this config/mode) split over the
    paid providers the run calls, else the a-priori upper bound. Returns (costs, source)."""
    from routing_study.eval.estimate import apriori_costs, list_prices, measured_cost
    from routing_study.llm import model_configs

    paid = {c.provider for _, c in model_configs(settings, roles) if c.provider != "ollama"}
    if not paid:
        return {}, "free"
    measured = measured_cost(settings.experiment_id, mode)
    if measured is not None and len(paid) == 1:
        return {next(iter(paid)): measured}, "measured"
    apriori, _ = apriori_costs(settings, mode, await list_prices(settings))
    if measured is not None:
        total = sum(apriori.values()) or 1.0
        return {p: measured * v / total for p, v in apriori.items()}, "measured (split a priori)"
    return apriori, "a priori upper bound"


# ---------------------------------------------------------------- execution


class ManifestLog:
    def __init__(self, path: Path, echo: Callable[[str], Any] = print) -> None:
        self.path, self.echo = path, echo

    def __call__(self, msg: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
        self.echo(line)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


async def _execute_once(run: ManifestRun, settings: Any, split: str, cases: list[Case], per_turn):
    from routing_study.eval.runner import Runner

    runner = Runner(
        settings,
        split=split,
        mode=run.mode,
        run_name=run.name,
        reps=run.reps,
        concurrency=run.concurrency,
        resume=True,
        budget_per_turn=per_turn,
    )
    return await runner.run(cases)


def execute(
    manifest: Manifest,
    manifest_path: Path,
    *,
    only: list[str] | None = None,
    dry_run: bool = False,
    echo: Callable[[str], Any] = print,
    data_dir: Path = Path("data"),
    run_once: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Run the manifest; returns run name -> final state (complete / flagged / aborted /
    skipped). `run_once(run, settings, split, cases, per_turn)` is the coroutine that
    executes one resume pass (tests inject a fake)."""
    from routing_study.budget import BudgetExceededError
    from routing_study.eval.rescore import rescore_file

    run_once = run_once or _execute_once
    log = ManifestLog(manifest.results_dir / f"manifest-{manifest_path.stem}.log", echo)
    states: dict[str, str] = {}
    for run in manifest.ordered(only):
        split = manifest.split_of(run)
        try:
            cases = select_cases(run, split, data_dir)
            settings = load_run_settings(run)
        except (OSError, ValueError) as exc:
            log(f"ABORT {run.name}: {exc}")
            states[run.name] = "aborted"
            continue
        problems = version_problems(run, settings, split)
        st = status(manifest, run, cases, read_rows(manifest.results_dir, run.name))
        problems += row_version_problems(st, settings)
        if problems:
            log(f"ABORT {run.name}: " + "; ".join(problems))
            states[run.name] = "aborted"
            continue
        while True:
            if st["complete"]:
                log(f"COMPLETE {run.name}: {_fmt(st)}")
                states[run.name] = "complete"
                break
            if st["missing"] == 0:  # above the error budget
                if st["retries_used"] >= manifest.max_infra_retries:
                    log(
                        f"FLAGGED {run.name}: error rate {100 * st['error_rate']:.1f}% > "
                        f"{100 * manifest.error_budget:.0f}% after {st['retries_used']} infra "
                        "retries: fix the infrastructure and redo this run from scratch "
                        "(pre-registered rule; never auto-deleted)"
                    )
                    states[run.name] = "flagged"
                    break
                if dry_run:
                    log(f"PLAN {run.name}: retry {st['retries_used'] + 1} of the error rows")
                    states[run.name] = "planned"
                    break
                dest = quarantine_errors(manifest.results_dir, run.name)
                log(f"RETRY {run.name}: error rows moved to {dest.name}")
                st = status(manifest, run, cases, read_rows(manifest.results_dir, run.name))
            roles = run_roles(settings, run, split)
            per_turn, source = asyncio.run(turn_cost(settings, run.mode, roles))
            projected = {p: round(v * st["missing"], 4) for p, v in per_turn.items()}
            log(f"{'PLAN' if dry_run else 'RUN'} {run.name}: {_fmt(st)}; {source} {projected}")
            if dry_run:
                states[run.name] = "planned"
                break
            try:
                out = asyncio.run(run_once(run, settings, split, cases, per_turn))
            except BudgetExceededError as exc:
                log(f"BUDGET {run.name}: {exc}; stopping the manifest")
                states[run.name] = "budget"
                return states
            rescored, _ = rescore_file(out, RESCORED, data_dir=data_dir)
            log(f"RESCORED {run.name} -> {rescored}")
            st = status(manifest, run, cases, read_rows(manifest.results_dir, run.name))
            if st["missing"]:
                log(f"INCOMPLETE {run.name}: {_fmt(st)}; stopping (inspect before resuming)")
                states[run.name] = "incomplete"
                break
    return states


def _fmt(st: dict[str, Any]) -> str:
    return (
        f"{st['present']}/{st['wanted']} keys, {st['missing']} missing, {st['errors']} errors "
        f"({100 * st['error_rate']:.1f}%), retries {st['retries_used']}"
    )


def manifest_report_paths(manifest: Manifest, split: str | None = None) -> list[Path]:
    """Rescored files of the manifest's runs (of `split` when given) that exist."""
    runs = [r for r in manifest.runs if split is None or manifest.split_of(r) == split]
    return [p for r in runs if (p := RESCORED / f"{r.name}.jsonl").exists()]
