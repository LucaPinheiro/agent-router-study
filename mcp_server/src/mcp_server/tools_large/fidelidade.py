"""Skill fidelidade_cashback (adjacent domain): get_points_balance, get_points_statement,
redeem_points, claim_missing_points, get_cashback_status, get_loyalty_tier."""

from datetime import timedelta
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    READ,
    TODAY,
    WRITE,
    ToolFailure,
    brl,
    days_from_today,
    get_customer,
    ok,
    protocol,
    resolve_order,
)
from mcp_server.large.data import CASHBACK_BY_ORDER, LOYALTY, SLA, W, days_since, large_tool
from mcp_server.large.models import (
    CashbackResult,
    LoyaltyTierResult,
    MissingPointsResult,
    PointsBalanceResult,
    PointsEntry,
    PointsRedeemResult,
    PointsStatementResult,
)
from mcp_server.models import Money

SKILL = "fidelidade_cashback"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]
BENEFITS = {
    "bronze": ["1 ponto por real em compras entregues"],
    "prata": ["1 ponto por real", "frete grátis em 2 pedidos por mês"],
    "ouro": ["1,5 ponto por real", "frete grátis ilimitado", "atendimento prioritário"],
    "diamante": [
        "2 pontos por real",
        "frete grátis ilimitado",
        "atendimento prioritário",
        "troca sem custo de postagem",
    ],
}
REWARD_VALUE = {"vale_compra": 0.01, "frete_gratis": 0.008, "doacao": 0.01}  # R$ per point


def _account() -> dict:
    return LOYALTY[get_customer()["id"]]


@large_tool(
    skill=SKILL,
    scope="loyalty:read",
    title="Saldo de pontos",
    annotations=READ,
    result=PointsBalanceResult,
    description="""
Mostra o saldo de pontos do programa de fidelidade: pontos disponíveis, pendentes, a vencer e \
o nível atual.
WHEN TO USE: "quantos pontos eu tenho?", "tenho pontos para vencer?".
DON'T USE FOR: extrato detalhado (use get_points_statement); pontos de uma compra que não \
caíram (use claim_missing_points); saldo de vale-presente (use get_gift_card_balance).
PARAMETERS: nenhum; o cliente vem da requisição autenticada.
CONFIRMATION: não requer.
RESULT: saldo e vencimento; repasse sem alterar.
""",
    examples=[
        "Quantos pontos eu tenho no programa?",
        "Tenho pontos para vencer este mês?",
        "Qual meu saldo de pontos da loja?",
        "Quantos pontos ainda estão pendentes?",
    ],
    keywords=["pontos", "saldo de pontos", "fidelidade", "programa", "pontos a vencer"],
)
async def get_points_balance() -> ToolResult:
    a = _account()
    result = PointsBalanceResult(
        customer_id=a["customer_id"],
        points=a["points"],
        pending_points=a["pending_points"],
        expiring_points=a["expiring_points"],
        expiring_at=a["expiring_at"],
        tier=a["tier"],
    )
    return ok(
        result,
        f"Saldo: {a['points']} pontos disponíveis e {a['pending_points']} pendentes (nível "
        f"{a['tier']}); {a['expiring_points']} vencem em {a['expiring_at']}.",
    )


@large_tool(
    skill=SKILL,
    scope="loyalty:read",
    title="Extrato de pontos",
    annotations=READ,
    result=PointsStatementResult,
    description="""
Lista o extrato de pontos (créditos por compra, bônus, resgates) dos últimos meses.
WHEN TO USE: "de onde vieram meus pontos?", "quero ver o extrato do programa", conferir se uma \
compra pontuou.
DON'T USE FOR: só o saldo (use get_points_balance); reclamar pontos de compra que não caíram \
(use claim_missing_points).
PARAMETERS: months = meses para trás (1 a 24, padrão 12).
CONFIRMATION: não requer.
RESULT: lançamentos em ordem de data; repasse sem alterar.
""",
    examples=[
        "Quero ver o extrato dos meus pontos",
        "De onde vieram os pontos que tenho?",
        "Minha última compra já pontuou?",
        "Mostra os resgates de pontos que fiz",
    ],
    keywords=["extrato de pontos", "historico", "lancamentos", "creditos", "resgates"],
)
async def get_points_statement(
    months: Annotated[int, Field(description="Meses para trás (1 a 24)", ge=1, le=24)] = 12,
) -> ToolResult:
    a = _account()
    since = (TODAY - timedelta(days=30 * months)).isoformat()
    entries = [PointsEntry(**e) for e in a["statement"] if e["date"] >= since]
    result = PointsStatementResult(
        customer_id=a["customer_id"], since=since, entries=entries, balance=a["points"]
    )
    lines = "; ".join(f"{e.date} {e.description} {e.points:+d}" for e in entries) or "nenhum"
    return ok(result, f"Extrato desde {since}: {lines}. Saldo {a['points']} pontos.")


@large_tool(
    skill=SKILL,
    scope="loyalty:write",
    title="Trocar pontos",
    annotations=WRITE,
    result=PointsRedeemResult,
    description="""
Troca pontos do programa por vale-compra, frete grátis ou doação (mínimo 500 pontos, múltiplos \
de 100).
WHEN TO USE: "quero trocar meus pontos", "dá para usar os pontos como desconto?".
DON'T USE FOR: ativar vale-presente (use redeem_gift_card); cupom (use validate_coupon); \
consultar saldo (use get_points_balance).
PARAMETERS: points = pontos a trocar; reward = vale_compra | frete_gratis | doacao.
CONFIRMATION: não requer.
RESULT: código do benefício, valor e pontos restantes; repasse sem alterar.
""",
    examples=[
        "Quero trocar 1000 pontos por um vale-compra",
        "Dá para usar meus pontos como desconto?",
        "Troca meus pontos por frete grátis",
        "Quero doar meus pontos para a campanha social",
    ],
    keywords=["trocar pontos", "resgatar pontos", "usar pontos", "converter pontos"],
)
async def redeem_points(
    points: Annotated[int, Field(description="Pontos a trocar (múltiplo de 100)", ge=100)],
    reward: Annotated[
        Literal["vale_compra", "frete_gratis", "doacao"], Field(description="Benefício")
    ] = "vale_compra",
) -> ToolResult:
    a = _account()
    if points < W["points_min_redeem"] or points % 100:
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"A troca mínima é de {W['points_min_redeem']} pontos, em múltiplos de 100.",
            recoverable=True,
        )
    if points > a["points"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Saldo insuficiente: o cliente tem {a['points']} pontos.",
            recoverable=True,
            details={"available_points": a["points"]},
        )
    voucher = protocol("PTS", "redeem_points", {"points": points, "reward": reward})
    value = Money(amount=round(points * REWARD_VALUE[reward], 2))
    result = PointsRedeemResult(
        protocol=voucher,
        points=points,
        reward=reward,
        voucher_code=voucher,
        value=value,
        remaining_points=a["points"] - points,
    )
    return ok(
        result,
        f"{points} pontos trocados por {reward} de {brl(value)}: código {voucher}. Restam "
        f"{a['points'] - points} pontos.",
    )


@large_tool(
    skill=SKILL,
    scope="loyalty:write",
    title="Reclamar pontos não creditados",
    annotations=WRITE,
    result=MissingPointsResult,
    description="""
Abre reclamação de pontos de uma compra entregue que não caíram após o prazo de crédito de 7 \
dias.
WHEN TO USE: "a compra não gerou pontos", "meus pontos não caíram".
DON'T USE FOR: cashback que não caiu (use get_cashback_status); reembolso que não caiu (use \
get_refund_status); consultar o extrato (use get_points_statement).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: protocolo, pontos previstos e prazo; repasse sem alterar.
""",
    examples=[
        "Minha compra não gerou pontos no programa",
        "Os pontos da compra do mês passado não caíram",
        "Recebi o pedido faz semanas e os pontos não apareceram",
        "Faltaram pontos da minha última compra",
    ],
    keywords=["pontos nao cairam", "faltam pontos", "nao pontuou", "pontos da compra"],
)
async def claim_missing_points(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    a = LOYALTY[o["customer_id"]]
    if not o["delivered_at"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} ainda não foi entregue; os pontos só contam após a entrega.",
            recoverable=False,
            suggested_tool="get_points_balance",
        )
    if any(e["order_id"] == o["id"] for e in a["statement"]):
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Os pontos do pedido {o['id']} já foram creditados.",
            recoverable=False,
            suggested_tool="get_points_statement",
        )
    if days_since(o["delivered_at"]) <= W["points_credit_days_after_delivery"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Os pontos do pedido {o['id']} são creditados até "
            f"{W['points_credit_days_after_delivery']} dias após a entrega; ainda estão "
            "pendentes.",
            recoverable=False,
            suggested_tool="get_points_balance",
        )
    proto = protocol("PTF", "claim_missing_points", {"order_id": o["id"]})
    pts = int(o["total"]["amount"])
    until = days_from_today(SLA["missing_points_days"])
    result = MissingPointsResult(
        order_id=o["id"], protocol=proto, expected_points=pts, expected_by=until
    )
    return ok(
        result,
        f"Reclamação {proto} aberta: {pts} pontos do pedido {o['id']}, crédito previsto até "
        f"{until}.",
    )


@large_tool(
    skill=SKILL,
    scope="loyalty:read",
    title="Status do cashback",
    annotations=READ,
    result=CashbackResult,
    description="""
Consulta o cashback de uma compra (campanha Cashback Pix): valor, status e data de liberação.
WHEN TO USE: "meu cashback já caiu?", "quando libera o cashback da compra?".
DON'T USE FOR: estorno ou reembolso (use get_refund_status); pontos do programa (use \
get_points_balance ou claim_missing_points).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: valor, status e liberação; repasse sem alterar.
""",
    examples=[
        "Meu cashback já caiu?",
        "Quando libera o cashback da compra que paguei no Pix?",
        "Quanto vou ganhar de cashback nesse pedido?",
        "O cashback da minha compra ainda está pendente?",
    ],
    keywords=["cashback", "dinheiro de volta pix", "libera", "credito de cashback"],
)
async def get_cashback_status(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    cb = CASHBACK_BY_ORDER.get(o["id"])
    if cb is None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} não participa de campanha de cashback (só compras pagas com Pix).",
            recoverable=False,
        )
    result = CashbackResult(
        order_id=o["id"],
        promotion_id=cb["promotion_id"],
        amount=Money(**cb["amount"]),
        cashback_status=cb["status"],
        release_at=cb["release_at"],
    )
    when = f", liberação em {cb['release_at']}" if cb["release_at"] else ""
    return ok(
        result,
        f"Cashback do pedido {o['id']}: {brl(cb['amount'])}, status {cb['status']}{when}.",
    )


@large_tool(
    skill=SKILL,
    scope="loyalty:read",
    title="Nível no programa",
    annotations=READ,
    result=LoyaltyTierResult,
    description="""
Mostra o nível do cliente no programa de fidelidade (bronze, prata, ouro, diamante), os \
benefícios e quanto falta para o próximo nível.
WHEN TO USE: "qual meu nível no programa?", "quanto falta para virar ouro?", "que benefícios \
eu tenho?".
DON'T USE FOR: saldo de pontos (use get_points_balance); dados do cadastro (use \
get_customer_profile).
PARAMETERS: nenhum; o cliente vem da requisição autenticada.
CONFIRMATION: não requer.
RESULT: nível, benefícios e progresso; repasse sem alterar.
""",
    examples=[
        "Qual é o meu nível no programa de fidelidade?",
        "Quanto falta para eu virar cliente ouro?",
        "Que benefícios eu tenho no meu nível?",
        "Meu nível dá frete grátis?",
    ],
    keywords=["nivel", "categoria", "ouro", "diamante", "beneficios", "programa"],
)
async def get_loyalty_tier() -> ToolResult:
    a = _account()
    result = LoyaltyTierResult(
        customer_id=a["customer_id"],
        tier=a["tier"],
        lifetime_points=a["lifetime_points"],
        next_tier=a["next_tier"],
        points_to_next_tier=a["points_to_next_tier"],
        benefits=BENEFITS[a["tier"]],
    )
    nxt = (
        f" Faltam {a['points_to_next_tier']} pontos para o nível {a['next_tier']}."
        if a["next_tier"]
        else " É o nível mais alto."
    )
    return ok(
        result,
        f"Nível {a['tier']} ({a['lifetime_points']} pontos acumulados). Benefícios: "
        f"{'; '.join(BENEFITS[a['tier']])}.{nxt}",
    )
