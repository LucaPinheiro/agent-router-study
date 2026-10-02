"""E2E smoke of the large catalog (T3.3): E0-L and E9-L on 5 hand-written dev-like messages.

There is no dev-L dataset yet, so the cases live here. They cover new skills (assinaturas,
notas_fiscais_cadastro, marketplace_vendedores, cartao_loja_crediario, fidelidade_cashback) on
mock entities whose target tool completes (mcp_server/MOCK_DB_NOTES_LARGE.md).

Needs `mcp-server-large` on :8766 (make up-app), Langfuse, app Redis and AWS (+ OpenRouter
for Jev). Results go to results/smoke_l/ (never the phase-1 results). The executor spend is
metered into the shared ledger as usual.

    uv run python scripts/smoke_large.py                 # E0-L x 5 + E9-L x 2 (Jev)
    uv run python scripts/smoke_large.py --e9-cases 5    # E9-L on all 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from routing_study.eval import runner as runner_mod
from routing_study.eval.runner import Case, Runner
from routing_study.settings import load_settings
from routing_study.tracing.langfuse import init as tracing_init

OUT_DIR = Path("results/smoke_l")
CASES = [
    Case(
        id="smoke-l-001",
        category="direto",
        customer_id="C001",
        turns=[
            {
                "role": "user",
                "content": "Vou viajar no mês que vem, dá para pausar minha "
                "assinatura de cápsulas por um ciclo?",
            }
        ],
        expected={
            "acceptable_skills": ["assinaturas"],
            "acceptable_tools": ["pause_subscription"],
            "args": {"cycles": 1},
        },
    ),
    Case(
        id="smoke-l-002",
        category="direto",
        customer_id="C016",
        turns=[
            {
                "role": "user",
                "content": "Comprei o fone do pedido O0048 no CNPJ da empresa e "
                "vou devolver. A transportadora pediu a nota de devolução, como faço?",
            }
        ],
        expected={
            "acceptable_skills": ["notas_fiscais_cadastro"],
            "acceptable_tools": ["issue_return_invoice"],
            "args": {"order_id": "O0048"},
        },
    ),
    Case(
        id="smoke-l-003",
        category="direto",
        customer_id="C009",
        turns=[
            {
                "role": "user",
                "content": "A jaqueta do pedido O0026 é de uma loja parceira do "
                "site. Já foi postada? Qual o rastreio do vendedor?",
            }
        ],
        expected={
            "acceptable_skills": ["marketplace_vendedores"],
            "acceptable_tools": ["track_seller_shipment"],
            "args": {"order_id": "O0026"},
        },
    ),
    Case(
        id="smoke-l-004",
        category="direto",
        customer_id="C016",
        turns=[
            {
                "role": "user",
                "content": "Recebi o pedido O0048 faz mais de uma semana e os "
                "pontos do programa ainda não entraram.",
            }
        ],
        expected={
            "acceptable_skills": ["fidelidade_cashback"],
            "acceptable_tools": ["claim_missing_points"],
            "args": {"order_id": "O0048"},
        },
    ),
    Case(
        id="smoke-l-005",
        category="direto",
        customer_id="C002",
        turns=[
            {"role": "user", "content": "Quanto deu a fatura do meu cartão da loja e quando vence?"}
        ],
        expected={
            "acceptable_skills": ["cartao_loja_crediario"],
            "acceptable_tools": ["get_card_bill"],
            "args": {},
        },
    ),
]


def summarize(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    out = []
    for r in rows:
        out.append(
            {
                "case": r["case_id"],
                "trace_id": r.get("trace_id"),
                "error": r.get("error"),
                "loaded_skill": r.get("loaded_skill"),
                "router_skill": (r.get("skill") or {}).get("choice"),
                "router_tool": (r.get("tool") or {}).get("choice"),
                "calls": [(c["name"], c["status"]) for c in r.get("calls") or []],
                "cost_billed": round((r.get("cost_usd") or {}).get("billed_total", 0.0), 5),
                "catalog_hash": r.get("catalog_hash"),
            }
        )
    return out


async def main(e9_cases: int) -> None:
    # like the CLI callback: Langfuse's client reads the process env (Settings reads .env itself)
    load_dotenv(".env")
    tracing_init()
    runner_mod.RESULTS_DIR = OUT_DIR  # never next to the phase-1 results
    plan = [
        ("config/experiments_l/e0_native_l.yaml", CASES),
        ("config/experiments_l/e9_regex_jev_llm_l.yaml", CASES[:e9_cases]),
    ]
    total = 0.0
    for config, cases in plan:
        settings = load_settings(config)
        assert settings.mcp_url.endswith(":8766/mcp"), settings.mcp_url
        name = f"smoke-l-{Path(config).stem}"
        runner = Runner(
            settings, split="smoke_l", mode="e2e", run_name=name, concurrency=1, overwrite=True
        )
        out = await runner.run(cases)
        rows = summarize(out)
        total += sum(r["cost_billed"] for r in rows)
        print(f"== {name} ({len(cases)} cases) -> {out}")
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
    print(f"total billed (executor + routing): US$ {total:.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--e9-cases", type=int, default=2, help="E9-L cases (Jev on OpenRouter)")
    asyncio.run(main(ap.parse_args().e9_cases))
