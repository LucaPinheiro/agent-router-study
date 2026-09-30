"""Benchmark a local (Ollama) LLM router on N dev cases: latency, peak memory, accuracy.

Usage:
  uv run python scripts/analysis/bench_local.py config/experiments/e6b_llm_qwen3_local.yaml \\
      [--strategy llm_local] [--n 20] [--confidence self_reported|logprob]

Routes each case sequentially (one request at a time: latency is model time, not queueing)
through the strategy's LLMRouter at both levels (skill, then tool over the chosen skill's
tools), exactly like `study run --mode routing-only` scores it, with the response cache OFF.
The catalog comes from the in-process MCP server. Memory: peak `size` / `size_vram` of the
model in Ollama's `/api/ps` (weights + KV cache), sampled every 0.5 s. The model is
loaded (timed separately) and warmed up with one call before timing.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
from typing import Any

import httpx
from fastmcp import Client

from routing_study.catalog import fetch_catalog
from routing_study.eval.runner import load_cases
from routing_study.eval.scorers import routing_scores
from routing_study.graph.nodes import _routing_input as graph_routing_input
from routing_study.llm import preload_ollama, unload_ollama
from routing_study.routers.pipeline import build_routers
from routing_study.settings import load_settings


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))]


async def sample_memory(base: str, model: str, peak: dict[str, int], stop: asyncio.Event) -> None:
    async with httpx.AsyncClient(timeout=5) as http:
        while not stop.is_set():
            try:
                for m in (await http.get(f"{base}/api/ps")).json().get("models", []):
                    if m["name"] == model:
                        peak["size"] = max(peak.get("size", 0), int(m.get("size") or 0))
                        peak["vram"] = max(peak.get("vram", 0), int(m.get("size_vram") or 0))
                        peak["ctx"] = int(m.get("context_length") or 0)
            except httpx.HTTPError:
                pass
            try:
                await asyncio.wait_for(stop.wait(), 0.5)
            except TimeoutError:
                pass


def routing_input(turns: list[dict[str, str]], level: str, skill: str | None = None):
    """The graph's RoutingInput builder: loaded_skill='__global__' after a global skill (F9)."""
    return graph_routing_input({"case": {"turns": turns}}, level, loaded_skill=skill)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--strategy", default=None, help="default: the skill pipeline's 1st step")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--confidence", choices=["self_reported", "logprob"], default=None)
    args = ap.parse_args()

    from mcp_server.server import mcp

    s = load_settings(args.config)
    name = args.strategy or s.routing.skill.pipeline[0].strategy
    cfg = s.strategies.get(name)
    if cfg is None or cfg.provider != "ollama":
        raise SystemExit(f"{name}: not an Ollama LLM strategy in {args.config}")
    cfg.cache = False
    if args.confidence:
        cfg.confidence = args.confidence
    router = build_routers(s, {name})[name]
    catalog = await fetch_catalog(s, Client(mcp))
    cases = load_cases("dev", args.n)
    base = (cfg.base_url or s.ollama_base_url).rstrip("/").removesuffix("/v1")

    load_s = (await preload_ollama(s, {name}))[cfg.served_name]  # excluded from latency
    await router.route(routing_input(cases[0].turns, "skill"), catalog.skill_options())

    peak: dict[str, int] = {}
    stop = asyncio.Event()
    sampler = asyncio.create_task(sample_memory(base, cfg.served_name, peak, stop))
    lat: dict[str, list[float]] = {"skill": [], "tool": []}
    toks: list[int] = []
    scores: list[dict[str, Any]] = []
    fails = 0
    for case in cases:
        sk = await router.route(routing_input(case.turns, "skill"), catalog.skill_options())
        lat["skill"].append(sk.latency_ms)
        tool = None
        if sk.choice is not None:
            inp = routing_input(case.turns, "tool", sk.choice)
            tl = await router.route(inp, catalog.tool_options(sk.choice))
            lat["tool"].append(tl.latency_ms)
            toks.append(int(tl.usage.get("completion_tokens") or 0))
            tool = tl.choice
            fails += bool(tl.usage.get("parse_fail") or tl.usage.get("error"))
        fails += bool(sk.usage.get("parse_fail") or sk.usage.get("error"))
        scores.append(routing_scores(sk.choice, tool, case.expected))
    stop.set()
    await sampler
    await unload_ollama(s)  # leave nothing resident

    def acc(metric: str) -> float:
        return 100 * statistics.mean(r[metric] for r in scores)

    print(
        f"model {cfg.served_name} ({name}, confidence={cfg.confidence}) on {len(cases)} dev cases"
    )
    print(f"  model load               {load_s:6.1f} s")
    for level, xs in lat.items():
        if xs:
            print(
                f"  {level:<5} latency ms      p50 {pct(xs, 0.5):7.0f}   p95 {pct(xs, 0.95):7.0f}"
                f"   (n={len(xs)})"
            )
    if toks:
        print(f"  tool completion tokens   mean {statistics.mean(toks):.0f}")
    gb = 1024**3
    print(
        f"  peak memory (ollama ps)  {peak.get('size', 0) / gb:.1f} GB total, "
        f"{peak.get('vram', 0) / gb:.1f} GB GPU, context {peak.get('ctx', 0)}"
    )
    print(
        f"  accuracy %               skill {acc('skill_correct'):.1f}   "
        f"tool {acc('tool_correct'):.1f}   joint {acc('joint_correct'):.1f}   "
        f"parse/errors {fails}"
    )


if __name__ == "__main__":
    asyncio.run(main())
