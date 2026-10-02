"""Skill promocoes_precos: validate_coupon, report_coupon_not_applied, get_promotion_terms,
request_price_protection, get_gift_card_balance, redeem_gift_card."""

from datetime import date
from typing import Annotated, Any

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    PAYMENTS,
    READ,
    TODAY,
    WRITE,
    ToolFailure,
    brl,
    days_from_today,
    get_customer,
    ok,
    pick_sku,
    protocol,
    resolve_order,
)
from mcp_server.large.data import (
    COUPONS,
    CURRENT_PRICES,
    GIFT_CARDS,
    PROMOTIONS,
    SLA,
    W,
    days_since,
    large_tool,
)
from mcp_server.large.models import (
    CouponClaimResult,
    CouponResult,
    GiftCard,
    GiftCardBalanceResult,
    GiftCardRedeemResult,
    PriceProtectionResult,
    PromotionTermsResult,
)
from mcp_server.models import Money

SKILL = "promocoes_precos"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]
Code = Annotated[str, Field(description="Código do cupom como o cliente digitou", max_length=40)]


def _coupon(code: str) -> dict[str, Any]:
    c = COUPONS.get(code.strip().upper())
    if c is None:
        raise ToolFailure(
            "NOT_FOUND",
            f"Cupom {code.strip()} não existe; confira o código.",
            recoverable=True,
        )
    return c


def _coupon_problems(c: dict[str, Any], on: date, order: dict[str, Any] | None) -> list[str]:
    """Rules the coupon breaks on date `on` (and for `order`, when given)."""
    problems = []
    if not c["valid_from"] <= on.isoformat() <= c["valid_until"]:
        problems.append(f"válido de {c['valid_from']} a {c['valid_until']}")
    if order is not None:
        if order["total"]["amount"] < c["min_order"]["amount"]:
            problems.append(f"pedido mínimo de {brl(c['min_order'])}")
        if c["category"] and all(i["category"] != c["category"] for i in order["items"]):
            problems.append(f"só para a categoria {c['category']}")
        if c["first_purchase_only"]:
            problems.append("só na primeira compra")
    return problems


def _discount(c: dict[str, Any], order: dict[str, Any]) -> float:
    if c["kind"] == "percent":
        return round(order["total"]["amount"] * c["value"] / 100, 2)
    return float(c["value"])


@large_tool(
    skill=SKILL,
    scope="promotions:read",
    title="Validar cupom",
    annotations=READ,
    result=CouponResult,
    description="""
Verifica se um cupom de desconto existe e vale hoje: tipo, valor, pedido mínimo, categoria, \
validade e motivos de recusa.
WHEN TO USE: "esse cupom ainda vale?", "por que o cupom não funciona no carrinho?", antes de \
comprar.
DON'T USE FOR: cupom que não foi aplicado numa compra já feita (use \
report_coupon_not_applied); regulamento da campanha (use get_promotion_terms); vale-presente \
(use redeem_gift_card).
PARAMETERS: code = código digitado pelo cliente.
CONFIRMATION: não requer.
RESULT: regras e validade do cupom; repasse sem alterar.
""",
    examples=[
        "O cupom CASA50 ainda está valendo?",
        "Por que meu código de desconto não funciona no carrinho?",
        "Esse cupom serve para qualquer produto?",
        "Qual o valor mínimo para usar o cupom MODA20?",
    ],
    keywords=["cupom", "codigo de desconto", "cupom valido", "desconto", "vale hoje"],
)
async def validate_coupon(code: Code) -> ToolResult:
    get_customer()
    c = _coupon(code)
    problems = _coupon_problems(c, TODAY, None)
    result = CouponResult(
        code=c["code"],
        valid=not problems,
        kind=c["kind"],
        value=c["value"],
        min_order=Money(**c["min_order"]),
        category=c["category"],
        valid_until=c["valid_until"],
        first_purchase_only=c["first_purchase_only"],
        reasons=problems,
    )
    value = f"{c['value']}%" if c["kind"] == "percent" else brl({"amount": c["value"]})
    scope = f" em {c['category']}" if c["category"] else ""
    state = "válido" if not problems else "não vale hoje (" + "; ".join(problems) + ")"
    return ok(
        result,
        f"Cupom {c['code']}: {value}{scope}, pedido mínimo {brl(c['min_order'])}, até "
        f"{c['valid_until']}; {state}.",
    )


@large_tool(
    skill=SKILL,
    scope="promotions:write",
    title="Reclamar cupom não aplicado",
    annotations=WRITE,
    result=CouponClaimResult,
    description="""
Abre análise de um cupom válido que não foi descontado numa compra já feita; aprovado, a \
diferença volta como crédito.
WHEN TO USE: "usei o cupom e o desconto não entrou", "paguei sem o desconto do cupom".
DON'T USE FOR: saber se um cupom vale (use validate_coupon); preço que baixou depois da compra \
(use request_price_protection); estorno de compra (use request_refund).
PARAMETERS: code = cupom usado; order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: protocolo, crédito previsto e prazo; repasse sem alterar.
""",
    examples=[
        "Usei o cupom e o desconto não entrou no pedido",
        "Paguei o valor cheio, o código CASA50 não foi aplicado",
        "O cupom sumiu na hora de finalizar a compra",
        "Quero o desconto do cupom que não foi descontado",
    ],
    keywords=["cupom nao aplicado", "desconto nao entrou", "cupom nao funcionou", "valor cheio"],
)
async def report_coupon_not_applied(code: Code, order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    c = _coupon(code)
    if o["status"] == "cancelled":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} foi cancelado; não há desconto a creditar.",
            recoverable=False,
        )
    problems = _coupon_problems(c, date.fromisoformat(o["created_at"]), o)
    if problems:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O cupom {c['code']} não valia para o pedido {o['id']}: " + "; ".join(problems) + ".",
            recoverable=False,
            suggested_tool="validate_coupon",
        )
    credit = Money(amount=_discount(c, o))
    proto = protocol("AJC", "report_coupon_not_applied", {"order_id": o["id"], "code": c["code"]})
    until = days_from_today(SLA["coupon_adjustment_days"])
    result = CouponClaimResult(
        order_id=o["id"], code=c["code"], protocol=proto, expected_credit=credit, expected_by=until
    )
    return ok(
        result,
        f"Análise {proto} aberta: cupom {c['code']} no pedido {o['id']}, crédito previsto de "
        f"{brl(credit)} até {until}.",
    )


@large_tool(
    skill=SKILL,
    scope="public:read",
    title="Regulamento da promoção",
    annotations=READ,
    result=PromotionTermsResult,
    description="""
Mostra o regulamento de uma campanha da loja: período, cupons ligados e regras (cashback Pix, \
pontos em dobro, semanas temáticas).
WHEN TO USE: "quais as regras da promoção?", "até quando vai a campanha?", "o cashback Pix \
vale para quê?".
DON'T USE FOR: validar um cupom específico (use validate_coupon); regras gerais de troca ou \
entrega (use search_help_center).
PARAMETERS: promotion = id, nome ou cupom da campanha, como o cliente disse.
CONFIRMATION: não requer.
RESULT: regulamento e datas; repasse sem alterar.
""",
    examples=[
        "Quais são as regras da Semana da Casa?",
        "Até quando vai a promoção de pontos em dobro?",
        "Como funciona o cashback no Pix?",
        "Qual o regulamento da campanha do cupom MODA20?",
    ],
    keywords=["regulamento", "regras da promocao", "campanha", "ate quando", "promocao"],
)
async def get_promotion_terms(
    promotion: Annotated[
        str, Field(description="Id, nome ou cupom da campanha", min_length=3, max_length=80)
    ],
) -> ToolResult:
    q = promotion.strip().upper().replace(" ", "-")
    found = next(
        (
            p
            for p in PROMOTIONS.values()
            if q in (p["id"], p["name"].upper().replace(" ", "-")) or q in p["coupons"]
        ),
        None,
    )
    if found is None:
        raise ToolFailure(
            "NOT_FOUND",
            f"Nenhuma campanha corresponde a {promotion.strip()}.",
            recoverable=True,
            details={"options": sorted(PROMOTIONS)},
        )
    active = found["valid_from"] <= TODAY.isoformat() <= found["valid_until"]
    result = PromotionTermsResult(
        promotion_id=found["id"],
        name=found["name"],
        valid_from=found["valid_from"],
        valid_until=found["valid_until"],
        active=active,
        coupons=found["coupons"],
        terms=found["terms"],
    )
    return ok(
        result,
        f"{found['name']} ({found['id']}), de {found['valid_from']} a {found['valid_until']}"
        f"{'' if active else ', encerrada'}: {found['terms']}",
    )


@large_tool(
    skill=SKILL,
    scope="promotions:write",
    title="Proteção de preço",
    annotations=WRITE,
    result=PriceProtectionResult,
    description="""
Devolve como vale-compra a diferença quando o preço de um item baixou em até 15 dias da compra.
WHEN TO USE: "comprei e o preço caiu", "o produto ficou mais barato depois que paguei".
DON'T USE FOR: devolver o produto ou desistir (use create_return_request ou cancel_order); \
cupom não aplicado (use report_coupon_not_applied); estorno de pedido cancelado (use \
request_refund).
PARAMETERS: order_id opcional se o cliente tem um só pedido; sku opcional se o pedido tem um \
só item.
CONFIRMATION: não requer.
RESULT: preço pago, preço atual, crédito e código do vale; repasse sem alterar.
""",
    examples=[
        "Comprei o smartwatch e uma semana depois o preço caiu",
        "O produto ficou mais barato depois que eu paguei, tenho direito à diferença?",
        "Vi o mesmo tênis por menos no site, quero a diferença",
        "Baixaram o preço da jaqueta que acabei de comprar",
    ],
    keywords=["preco baixou", "diferenca de preco", "ficou mais barato", "protecao de preco"],
)
async def request_price_protection(
    order_id: OrderId = None,
    sku: Annotated[
        str | None, Field(description="SKU do item. Omita se o pedido tem um só item")
    ] = None,
) -> ToolResult:
    o = resolve_order(order_id)
    if o["status"] == "cancelled" or PAYMENTS[o["payment_id"]]["status"] != "approved":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} não está pago e ativo; não há diferença a creditar.",
            recoverable=False,
            suggested_tool="get_payment_status",
        )
    if days_since(o["created_at"]) > W["price_protection_days_after_purchase"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} foi feito há mais de {W['price_protection_days_after_purchase']}"
            " dias.",
            recoverable=False,
        )
    item = pick_sku(o, sku)
    now = CURRENT_PRICES.get(item["sku"])
    if now is None or now["amount"] >= item["unit_price"]["amount"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O preço de {item['name']} não baixou desde a compra.",
            recoverable=False,
        )
    credit = Money(
        amount=round((item["unit_price"]["amount"] - now["amount"]) * item["quantity"], 2)
    )
    code = protocol("VALE", "request_price_protection", {"order_id": o["id"], "sku": item["sku"]})
    expires = days_from_today(180)
    result = PriceProtectionResult(
        order_id=o["id"],
        sku=item["sku"],
        paid_price=Money(**item["unit_price"]),
        current_price=Money(**now),
        credit=credit,
        gift_card_code=code,
        expires_at=expires,
    )
    return ok(
        result,
        f"{item['name']} (pedido {o['id']}): pago {brl(item['unit_price'])}, hoje {brl(now)}. "
        f"Vale-compra {code} de {brl(credit)}, válido até {expires}.",
    )


@large_tool(
    skill=SKILL,
    scope="giftcards:read",
    title="Saldo de vale-presente",
    annotations=READ,
    result=GiftCardBalanceResult,
    description="""
Consulta o saldo e a validade dos vale-presentes e vale-compras já resgatados na conta do \
cliente.
WHEN TO USE: "quanto tenho de saldo no vale?", "meu vale-compra ainda vale?".
DON'T USE FOR: ativar um vale-presente novo (use redeem_gift_card); pontos do programa (use \
get_points_balance); cashback (use get_cashback_status).
PARAMETERS: code opcional; sem ele, lista todos os vales da conta.
CONFIRMATION: não requer.
RESULT: saldo e validade de cada vale; repasse sem alterar.
""",
    examples=[
        "Quanto ainda tenho de saldo no vale-presente?",
        "Meu vale-compra ainda está dentro da validade?",
        "Quais vales eu tenho na minha conta?",
        "Sobrou crédito do cartão-presente que usei?",
    ],
    keywords=["saldo do vale", "vale presente", "vale compra", "gift card", "cartao presente"],
)
async def get_gift_card_balance(
    code: Annotated[
        str | None, Field(description="Código do vale, se informado", max_length=40)
    ] = None,
) -> ToolResult:
    c = get_customer()
    owned = [g for g in GIFT_CARDS.values() if g["customer_id"] == c["id"]]
    if code:
        g = GIFT_CARDS.get(code.strip().upper())
        if g is not None and g["status"] == "unredeemed":
            raise ToolFailure(
                "NOT_ELIGIBLE",
                f"O vale {g['code']} ainda não foi resgatado na conta.",
                recoverable=False,
                suggested_tool="redeem_gift_card",
            )
        if g is None or g["customer_id"] != c["id"]:
            raise ToolFailure(
                "NOT_FOUND",
                f"Vale {code.strip()} não encontrado nesta conta.",
                recoverable=True,
                details={"options": [x["code"] for x in owned]},
            )
        owned = [g]
    if not owned:
        raise ToolFailure("NOT_FOUND", "O cliente não tem vales na conta.", recoverable=False)
    cards = [
        GiftCard(
            code=g["code"],
            card_status=g["status"],
            balance=Money(**g["balance"]),
            expires_at=g["expires_at"],
        )
        for g in owned
    ]
    total = Money(
        amount=round(sum(g.balance.amount for g in cards if g.card_status == "active"), 2)
    )
    result = GiftCardBalanceResult(gift_cards=cards, total_balance=total)
    text = "; ".join(
        f"{g.code}: {g.card_status}, saldo {brl(g.balance)}, validade {g.expires_at}" for g in cards
    )
    return ok(result, f"{text}. Saldo disponível: {brl(total)}.")


@large_tool(
    skill=SKILL,
    scope="giftcards:write",
    title="Resgatar vale-presente",
    annotations=WRITE,
    result=GiftCardRedeemResult,
    description="""
Resgata (ativa) na conta do cliente o código de um vale-presente recebido, liberando o saldo \
para compras.
WHEN TO USE: "ganhei um vale-presente, como uso?", "quero ativar o código do cartão-presente".
DON'T USE FOR: cupom de desconto (use validate_coupon); consultar saldo de vale já resgatado \
(use get_gift_card_balance); trocar pontos (use redeem_points).
PARAMETERS: code = código impresso no vale, como o cliente digitou.
CONFIRMATION: não requer.
RESULT: valor creditado e validade; repasse sem alterar.
""",
    examples=[
        "Ganhei um vale-presente de aniversário, como coloco na conta?",
        "Quero ativar o código PRESENTE-8H3T6W",
        "Recebi um cartão-presente da loja, como resgato?",
        "Como uso o código que veio no cartão de presente?",
    ],
    keywords=["resgatar vale", "ativar vale presente", "codigo do presente", "gift card"],
)
async def redeem_gift_card(code: Code) -> ToolResult:
    c = get_customer()
    g = GIFT_CARDS.get(code.strip().upper())
    if g is None:
        raise ToolFailure(
            "NOT_FOUND", f"Vale {code.strip()} não existe; confira o código.", recoverable=True
        )
    if g["status"] != "unredeemed":
        mine = g["customer_id"] == c["id"]
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O vale {g['code']} já foi resgatado"
            + (" nesta conta." if mine else " em outra conta."),
            recoverable=False,
            suggested_tool="get_gift_card_balance" if mine else None,
        )
    if g["expires_at"] < TODAY.isoformat():
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O vale {g['code']} venceu em {g['expires_at']}.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    proto = protocol("RVP", "redeem_gift_card", {"code": g["code"]})
    result = GiftCardRedeemResult(
        code=g["code"], protocol=proto, credited=Money(**g["value"]), expires_at=g["expires_at"]
    )
    return ok(
        result,
        f"Vale {g['code']} resgatado: {brl(g['value'])} creditados na conta, válidos até "
        f"{g['expires_at']}. Protocolo {proto}.",
    )
