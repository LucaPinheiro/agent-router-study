"""`study` CLI: run | rescore | report | simulate | estimate | budget | graph | trace."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Literal

import typer
from dotenv import load_dotenv

app = typer.Typer(no_args_is_help=True, add_completion=False)
Config = Annotated[
    Path,
    typer.Option(
        "--config", "-c", exists=True, dir_okay=False, help="config/experiments/eN_*.yaml"
    ),
]


@app.callback()
def _setup() -> None:
    # Langfuse's get_client() reads the process env only; Settings reads .env itself.
    load_dotenv(".env")
    from routing_study.tracing.langfuse import init

    init()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def run(
    config: Config,
    split: Annotated[str, typer.Option(help="dev | test")] = "dev",
    mode: Annotated[Literal["e2e", "routing-only"], typer.Option()] = "e2e",
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="N cases, stratified by category (fixed seed); omit for all"),
    ] = None,
    reps: Annotated[int, typer.Option(min=1)] = 1,
    concurrency: Annotated[int, typer.Option(min=1)] = 4,
    run_name: Annotated[str | None, typer.Option(help="Langfuse dataset run name")] = None,
    routing_mode: Annotated[
        Literal["single", "cascade", "shadow"] | None, typer.Option(help="override routing.mode")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option(help="replace an existing results/<run_name>.jsonl")
    ] = False,
) -> None:
    """Run one experiment config over a split; writes results/<run_name>.jsonl, then rescores it
    into results/rescored/ (the only input of reports)."""
    from routing_study.eval.report import render
    from routing_study.eval.rescore import rescore_file
    from routing_study.eval.runner import Runner, default_run_name, load_cases
    from routing_study.settings import load_settings

    settings = load_settings(config)
    if routing_mode:
        settings.routing.mode = routing_mode
    name = run_name or default_run_name(settings.experiment_id, split, mode)
    cases = load_cases(split, limit)
    runner = Runner(
        settings,
        split=split,
        mode=mode,
        run_name=name,
        reps=reps,
        concurrency=concurrency,
        overwrite=overwrite,
    )
    from routing_study.budget import BudgetExceededError

    try:
        out = asyncio.run(runner.run(cases))
    except BudgetExceededError as exc:
        typer.echo(f"ABORTED (budget guard): {exc}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(f"run {name}: {len(cases)} cases x {reps} reps -> {out}")
    rescored, _ = rescore_file(out, RESCORED)
    typer.echo(render([rescored]))


RESCORED = Path("results/rescored")


@app.command()
def rescore(
    files: Annotated[list[Path], typer.Argument(exists=True, help="raw results/*.jsonl")],
    out: Annotated[Path, typer.Option(help="output directory")] = RESCORED,
    data_dir: Annotated[Path, typer.Option(help="dir with dataset_<split>.jsonl")] = Path("data"),
    tools: Annotated[Path, typer.Option(help="MCP tools/list snapshot")] = Path(
        "mcp_server/tools_list.json"
    ),
    prices: Annotated[
        Path | None,
        typer.Option(help="saved OpenRouter GET /models JSON: adds the list-price column"),
    ] = None,
    run_git_sha: Annotated[
        str | None, typer.Option(help="run code version when the rows do not record it")
    ] = None,
) -> None:
    """Recompute every score offline from raw rows + dataset + tool schemas (with provenance)."""
    from routing_study.eval.rescore import describe, rescore_file

    for f in files:
        path, prov = rescore_file(
            f,
            out,
            data_dir=data_dir,
            tools_path=tools,
            prices_path=prices,
            run_git_sha=run_git_sha,
        )
        typer.echo(describe(path, prov))


@app.command()
def report(
    files: Annotated[
        list[Path] | None,
        typer.Argument(help="rescored results (default: results/rescored/*.jsonl)"),
    ] = None,
) -> None:
    """Accuracy / cost / latency per run, with 95% CIs, from RESCORED results files."""
    from routing_study.eval.report import render

    paths = files or sorted(RESCORED.glob("*.jsonl"))
    typer.echo(render(paths))


@app.command()
def simulate(
    results: Annotated[Path, typer.Argument(exists=True, help="rescored results of a shadow run")],
    config: Config,
) -> None:
    """Replay a config's cascade offline over the shadow decisions of a results file."""
    from routing_study.eval.simulate import render_simulation
    from routing_study.settings import load_settings

    typer.echo(render_simulation(results, load_settings(config)))


@app.command()
def estimate(
    config: Config,
    split: str = "test",
    mode: str = "e2e",
    reps: int = 3,
    limit: int | None = None,
) -> None:
    """Cost estimate for a run, before spending."""
    from routing_study.eval.estimate import estimate as do_estimate
    from routing_study.eval.runner import load_cases
    from routing_study.settings import load_settings

    settings = load_settings(config)
    typer.echo(asyncio.run(do_estimate(settings, len(load_cases(split, limit)), reps, mode)))


@app.command()
def budget(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="experiment YAML (caps / ledger path)")
    ] = None,
) -> None:
    """Spend recorded in the ledger, by provider and model, against the account caps."""
    from routing_study.budget import ACCOUNTS, SpendLedger, summarize
    from routing_study.settings import load_settings

    b = load_settings(config).budget
    ledger = SpendLedger(b.ledger_path, {"aws": b.aws_usd_cap, "openrouter": b.openrouter_usd_cap})
    rows = ledger.rows()
    typer.echo(f"ledger {b.ledger_path}: {len(rows)} calls")
    typer.echo(summarize(rows))
    for acct, cap in ledger.caps.items():
        providers = ", ".join(p for p, a in ACCOUNTS.items() if a == acct)
        spent = ledger.spent.get(acct, 0.0)
        typer.echo(f"{acct:<11} ({providers}) spent ${spent:.4f} of cap ${cap:.2f}")


@app.command()
def graph(out: Path = Path("docs/graph.md")) -> None:
    """Write the LangGraph topology as a mermaid diagram."""
    from routing_study.graph.builder import build_graph

    mermaid = build_graph().get_graph().draw_mermaid()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# Host graph\n\nGenerated by `uv run study graph`. Routing-only runs compile the same "
        'graph with `interrupt_before=["agent"]`; E0 (native) passes through `route_skill` '
        "and `route_tool`.\n\n```mermaid\n" + mermaid + "```\n",
        encoding="utf-8",
    )
    typer.echo(f"wrote {out}")


@app.command()
def trace(trace_id: str) -> None:
    """Print one trace's observation tree and scores from the Langfuse API."""
    from routing_study.tracing.langfuse import LangfuseAPI, format_tree

    api = LangfuseAPI()
    obs, scores = api.wait(trace_id, timeout_s=10)
    typer.echo(format_tree(obs))
    typer.echo(
        "scores: "
        + ", ".join(f"{s['name']}={s.get('value', s.get('stringValue'))}" for s in scores)
    )


if __name__ == "__main__":
    app()
