"""Skill assinaturas (recurring delivery): get_subscription, pause_subscription,
cancel_subscription, change_subscription_date, change_subscription_items,
update_subscription_payment."""

from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import DESTRUCTIVE, READ, WRITE, ToolFailure, brl, get_customer, ok, protocol
from mcp_server.large.data import (
    STORE_CARDS,
    W,
    customer_card_last4s,
    future_date,
    large_tool,
    resolve_subscription,
)
from mcp_server.large.models import SubscriptionChangeResult, SubscriptionItem, SubscriptionResult
from mcp_server.models import Money

SKILL = "assinaturas"
SubscriptionId = Annotated[
    str | None,
    Field(description="Assinatura (ex.: ASS-1A2B3C4D). Omita se o cliente tem uma só"),
]
SUB_CATALOG = {
    "CAP-CAFE-50": ("Cápsulas de café espresso (50 un.)", 89.90),
    "CAF-GRAO-1K": ("Café em grãos 1 kg", 64.90),
    "FIL-AGUA-3": ("Refil de filtro de água (3 un.)", 79.90),
    "RAC-CAO-10": ("Ração para cães adultos 10 kg", 159.90),
    "SAB-LIQ-5L": ("Sabão líquido 5 L", 54.90),
    "FRA-G-80": ("Fraldas tamanho G (80 un.)", 119.90),
}


def _items(raw: list[dict[str, Any]]) -> list[SubscriptionItem]:
    return [SubscriptionItem(**i) for i in raw]


def _price(items: list[SubscriptionItem]) -> Money:
    return Money(amount=round(sum(i.unit_price.amount * i.quantity for i in items), 2))


def _require(s: dict[str, Any], *statuses: str) -> None:
    if s["status"] not in statuses:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A assinatura {s['id']} está {s['status']}; esta alteração não se aplica.",
            recoverable=False,
            suggested_tool="get_subscription",
        )


@large_tool(
    skill=SKILL,
    scope="subscriptions:read",
    title="Consultar assinatura",
    annotations=READ,
    result=SubscriptionResult,
    description="""
Consulta uma assinatura de entrega recorrente: status, itens, frequência, próxima entrega e \
forma de pagamento.
WHEN TO USE: "quando chega a próxima entrega da assinatura?", "o que vem na minha assinatura?", \
"minha assinatura está ativa?".
DON'T USE FOR: situação de um pedido avulso (use get_order_status); cobrança de um pedido (use \
get_payment_status).
PARAMETERS: subscription_id opcional se o cliente tem uma só assinatura.
CONFIRMATION: não requer.
RESULT: dados da assinatura; repasse datas e valores sem alterar.
""",
    examples=[
        "Quando chega a próxima entrega da minha assinatura?",
        "Quais itens vêm no meu clube do café?",
        "Minha assinatura ainda está ativa?",
        "Quanto pago por mês na assinatura?",
    ],
    keywords=["assinatura", "recorrente", "clube", "proxima entrega", "plano mensal"],
)
async def get_subscription(subscription_id: SubscriptionId = None) -> ToolResult:
    s = resolve_subscription(subscription_id)
    items = _items(s["items"])
    result = SubscriptionResult(
        subscription_id=s["id"],
        plan_name=s["plan_name"],
        subscription_status=s["status"],
        items=items,
        frequency_days=s["frequency_days"],
        next_delivery=s["next_delivery"],
        paused_until=s["paused_until"],
        payment_method=s["payment_method"],
        card_last4=s["card_last4"],
        price_per_delivery=_price(items),
    )
    when = f", próxima entrega {s['next_delivery']}" if s["next_delivery"] else ""
    return ok(
        result,
        f"Assinatura {s['id']} ({s['plan_name']}): {s['status']}, a cada "
        f"{s['frequency_days']} dias, {brl(_price(items))} por entrega{when}.",
    )


@large_tool(
    skill=SKILL,
    scope="subscriptions:write",
    title="Pausar assinatura",
    annotations=WRITE,
    result=SubscriptionChangeResult,
    description="""
Pausa uma assinatura ativa por 1 a 3 ciclos, sem cancelar; a recorrência volta sozinha depois.
WHEN TO USE: "vou viajar, quero pular as próximas entregas", "pausa minha assinatura por um mês".
DON'T USE FOR: encerrar a assinatura (use cancel_subscription); só mudar o dia da próxima \
entrega (use change_subscription_date).
PARAMETERS: cycles = número de ciclos (1 a 3); subscription_id opcional se o cliente tem uma só.
CONFIRMATION: não requer.
RESULT: protocolo e data de retomada; repasse sem alterar.
""",
    examples=[
        "Vou viajar, quero pular as próximas entregas da assinatura",
        "Dá para dar um tempo na assinatura sem cancelar?",
        "Pausa o clube do café por dois meses",
        "Quero suspender temporariamente a ração recorrente",
    ],
    keywords=["pausar", "suspender", "pular entrega", "dar um tempo", "assinatura"],
)
async def pause_subscription(
    cycles: Annotated[int, Field(description="Ciclos a pular (1 a 3)", ge=1, le=3)] = 1,
    subscription_id: SubscriptionId = None,
) -> ToolResult:
    s = resolve_subscription(subscription_id)
    _require(s, "active")
    resume = (
        date.fromisoformat(s["next_delivery"]) + timedelta(days=s["frequency_days"] * cycles)
    ).isoformat()
    proto = protocol("PAU", "pause_subscription", {"id": s["id"], "cycles": cycles})
    result = SubscriptionChangeResult(
        subscription_id=s["id"],
        protocol=proto,
        subscription_status="paused",
        next_delivery=resume,
        paused_until=resume,
    )
    return ok(
        result,
        f"Assinatura {s['id']} pausada por {cycles} ciclo(s); as entregas voltam em {resume}. "
        f"Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="subscriptions:cancel",
    title="Cancelar assinatura",
    annotations=DESTRUCTIVE,
    result=SubscriptionChangeResult,
    description="""
Cancela uma assinatura de entrega recorrente, sem multa; as próximas cobranças e entregas \
param. Irreversível: voltar exige nova assinatura.
WHEN TO USE: "quero cancelar minha assinatura", "não quero mais receber todo mês".
DON'T USE FOR: cancelar um pedido avulso (use cancel_order); cancelar visita técnica (use \
cancel_service_order); parar só por um tempo (use pause_subscription).
PARAMETERS: subscription_id opcional se o cliente tem uma só; reason opcional.
CONFIRMATION: o servidor não pede confirmação; a ação é irreversível.
RESULT: protocolo do cancelamento; repasse sem alterar.
""",
    examples=[
        "Quero cancelar minha assinatura do clube do café",
        "Não quero mais receber a ração todo mês, encerra o plano",
        "Pode desativar a entrega recorrente?",
        "Cancela a assinatura de fraldas",
    ],
    keywords=["cancelar assinatura", "encerrar plano", "parar recorrencia", "desativar"],
)
async def cancel_subscription(
    subscription_id: SubscriptionId = None,
    reason: Annotated[
        str | None, Field(description="Motivo dito pelo cliente, se houver", max_length=300)
    ] = None,
) -> ToolResult:
    s = resolve_subscription(subscription_id)
    _require(s, "active", "paused")
    proto = protocol("CAS", "cancel_subscription", {"id": s["id"], "reason": reason})
    result = SubscriptionChangeResult(
        subscription_id=s["id"], protocol=proto, subscription_status="cancelled"
    )
    return ok(
        result,
        f"Assinatura {s['id']} ({s['plan_name']}) cancelada; não haverá novas cobranças nem "
        f"entregas. Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="subscriptions:write",
    title="Mudar data da assinatura",
    annotations=WRITE,
    result=SubscriptionChangeResult,
    description="""
Muda a data da próxima entrega de uma assinatura ativa (de 1 a 30 dias à frente); as seguintes \
seguem a frequência a partir dela.
WHEN TO USE: "quero receber a assinatura no dia 10", "adianta a próxima entrega do clube".
DON'T USE FOR: data de entrega de um pedido avulso (use reschedule_delivery); dia do técnico \
(use reschedule_technical_visit); pular entregas (use pause_subscription).
PARAMETERS: new_date em AAAA-MM-DD; subscription_id opcional se o cliente tem uma só.
CONFIRMATION: não requer.
RESULT: protocolo e nova data; repasse sem alterar.
""",
    examples=[
        "Quero que a assinatura chegue sempre no começo do mês",
        "Dá para adiantar a próxima entrega do clube do café?",
        "Muda a entrega recorrente para o dia 15",
        "Prefiro receber a ração uma semana depois",
    ],
    keywords=["data da assinatura", "dia da entrega recorrente", "adiantar", "mudar dia"],
)
async def change_subscription_date(
    new_date: Annotated[str, Field(description="Nova data da próxima entrega, AAAA-MM-DD")],
    subscription_id: SubscriptionId = None,
) -> ToolResult:
    s = resolve_subscription(subscription_id)
    _require(s, "active")
    when = future_date(
        new_date, W["subscription_date_min_days_ahead"], W["subscription_date_max_days_ahead"]
    )
    proto = protocol("DTA", "change_subscription_date", {"id": s["id"], "date": when.isoformat()})
    result = SubscriptionChangeResult(
        subscription_id=s["id"],
        protocol=proto,
        subscription_status=s["status"],
        next_delivery=when.isoformat(),
    )
    return ok(
        result,
        f"Próxima entrega da assinatura {s['id']} alterada para {when.isoformat()}. "
        f"Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="subscriptions:write",
    title="Alterar itens da assinatura",
    annotations=WRITE,
    result=SubscriptionChangeResult,
    description="""
Inclui, remove ou muda a quantidade de um item da assinatura (quantity 0 remove o item).
WHEN TO USE: "quero acrescentar café em grãos na assinatura", "manda 3 pacotes em vez de 2", \
"tira o sabão da assinatura".
DON'T USE FOR: trocar tamanho ou cor de um pedido entregue (use create_exchange); cancelar a \
assinatura toda (use cancel_subscription).
PARAMETERS: sku do catálogo de assinatura; quantity de 0 a 10; subscription_id opcional se o \
cliente tem uma só.
CONFIRMATION: não requer.
RESULT: itens e novo valor por entrega; repasse sem alterar.
""",
    examples=[
        "Quero acrescentar café em grãos na minha assinatura",
        "Manda três caixas de cápsulas em vez de duas",
        "Tira o sabão líquido da entrega recorrente",
        "Dá para incluir refil de filtro no meu plano?",
    ],
    keywords=["itens da assinatura", "incluir", "remover", "quantidade", "acrescentar"],
)
async def change_subscription_items(
    sku: Annotated[str, Field(description="SKU do catálogo de assinatura (ex.: CAP-CAFE-50)")],
    quantity: Annotated[int, Field(description="Nova quantidade; 0 remove o item", ge=0, le=10)],
    subscription_id: SubscriptionId = None,
) -> ToolResult:
    s = resolve_subscription(subscription_id)
    _require(s, "active", "paused")
    code = sku.strip().upper()
    if code not in SUB_CATALOG:
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"{sku} não faz parte do catálogo de assinatura.",
            recoverable=True,
            details={"options": sorted(SUB_CATALOG)},
        )
    items = {i["sku"]: dict(i) for i in s["items"]}
    if quantity == 0:
        items.pop(code, None)
    else:
        name, price = SUB_CATALOG[code]
        items[code] = {
            "sku": code,
            "name": name,
            "quantity": quantity,
            "unit_price": {"amount": price, "currency": "BRL"},
        }
    if not items:
        raise ToolFailure(
            "VALIDATION_ERROR",
            "A assinatura precisa de ao menos um item; para encerrar, cancele a assinatura.",
            recoverable=True,
        )
    new_items = _items(list(items.values()))
    proto = protocol(
        "ITS", "change_subscription_items", {"id": s["id"], "sku": code, "quantity": quantity}
    )
    result = SubscriptionChangeResult(
        subscription_id=s["id"],
        protocol=proto,
        subscription_status=s["status"],
        items=new_items,
        price_per_delivery=_price(new_items),
    )
    listing = ", ".join(f"{i.quantity}x {i.name}" for i in new_items)
    return ok(
        result,
        f"Assinatura {s['id']} atualizada: {listing}; {brl(_price(new_items))} por entrega. "
        f"Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="subscriptions:write",
    title="Trocar pagamento da assinatura",
    annotations=WRITE,
    result=SubscriptionChangeResult,
    description="""
Troca a forma de pagamento das próximas cobranças da assinatura: cartão de crédito já usado na \
loja, Pix ou cartão da loja.
WHEN TO USE: "meu cartão venceu, quero pagar a assinatura com outro", "passa a assinatura para \
o Pix".
DON'T USE FOR: pagamento de um pedido avulso (use get_payment_status); dados de faturamento \
da nota (use update_billing_data).
PARAMETERS: method = credit_card | pix | cartao_loja; card_last4 = final do cartão, só para \
credit_card; nunca peça o número completo. subscription_id opcional se o cliente tem uma só.
CONFIRMATION: não requer.
RESULT: protocolo e nova forma de pagamento; repasse sem alterar.
""",
    examples=[
        "Meu cartão venceu, quero pagar a assinatura com outro",
        "Passa a cobrança da assinatura para o Pix",
        "Quero usar o cartão final 3340 nas próximas cobranças do clube",
        "Dá para pagar a assinatura com o cartão da loja?",
    ],
    keywords=["pagamento da assinatura", "trocar cartao", "forma de pagamento", "cobranca mensal"],
)
async def update_subscription_payment(
    method: Annotated[
        Literal["credit_card", "pix", "cartao_loja"], Field(description="Nova forma de pagamento")
    ],
    card_last4: Annotated[
        str | None, Field(description="4 últimos dígitos do cartão (só credit_card)", max_length=4)
    ] = None,
    subscription_id: SubscriptionId = None,
) -> ToolResult:
    customer = get_customer()
    s = resolve_subscription(subscription_id)
    _require(s, "active", "paused")
    last4 = None
    if method == "credit_card":
        wallet = customer_card_last4s(customer)
        if not card_last4 or card_last4.strip() not in wallet:
            raise ToolFailure(
                "VALIDATION_ERROR",
                "Informe o final de um cartão já usado em compras na loja.",
                recoverable=True,
                details={"options": wallet},
            )
        last4 = card_last4.strip()
    elif method == "cartao_loja":
        card = STORE_CARDS.get(customer["id"])
        if card is None or card["status"] != "active":
            raise ToolFailure(
                "NOT_ELIGIBLE",
                "O cliente não tem cartão da loja ativo.",
                recoverable=False,
            )
        last4 = card["last4"]
    proto = protocol(
        "PGA", "update_subscription_payment", {"id": s["id"], "method": method, "card_last4": last4}
    )
    result = SubscriptionChangeResult(
        subscription_id=s["id"],
        protocol=proto,
        subscription_status=s["status"],
        payment_method=method,
        card_last4=last4,
    )
    final = f" final {last4}" if last4 else ""
    return ok(
        result,
        f"Pagamento da assinatura {s['id']} alterado para {method}{final} a partir da próxima "
        f"cobrança. Protocolo {proto}.",
    )
