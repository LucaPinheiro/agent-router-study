"""Skill pedidos_logistica: get_order_status, track_shipment, update_delivery_address,
reschedule_delivery, cancel_order."""

import re
from datetime import date
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    DESTRUCTIVE,
    PAYMENTS,
    READ,
    REFUND_TEXT,
    SHIPMENTS,
    TODAY,
    WRITE,
    ToolFailure,
    after_delivery_next_step,
    brl,
    catalog_tool,
    fmt_address,
    money_back_next_step,
    ok,
    order_ref,
    protocol,
    refund_deadline,
    resolve_order,
)
from mcp_server.models import (
    Address,
    AddressUpdateResult,
    CancellationResult,
    Money,
    OrderItem,
    OrderStatusResult,
    RescheduleResult,
    ShipmentEvent,
    ShipmentResult,
)

SKILL = "pedidos_logistica"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]
NOT_SHIPPED = ("awaiting_payment", "processing")
UFS = set(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


@catalog_tool(
    skill=SKILL,
    scope="orders:read",
    title="Status do pedido",
    annotations=READ,
    result=OrderStatusResult,
    description="""
Consulta a situação de um pedido: status, itens, valor, forma de pagamento, previsão ou data \
de entrega e endereço.
WHEN TO USE: "como está meu pedido?", "meu pedido foi enviado?", ver itens ou valor de um pedido.
DON'T USE FOR: onde está o pacote e eventos de rastreio (use track_shipment); situação do \
pagamento (use get_payment_status) ou do reembolso (use get_refund_status).
PARAMETERS: order_id opcional se o cliente tem um só pedido; nunca invente o número.
CONFIRMATION: não requer.
RESULT: dados do pedido; repasse datas, valores e IDs sem alterar.
""",
    examples=[
        "Como está meu pedido O0002?",
        "Meu pedido já foi enviado?",
        "Quais itens vieram no meu último pedido?",
        "Qual a previsão de entrega da minha compra?",
    ],
    keywords=["status", "situacao", "pedido", "andamento", "previsao", "itens"],
)
async def get_order_status(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    pay = PAYMENTS[o["payment_id"]]
    result = OrderStatusResult(
        order=order_ref(o),
        items=[
            OrderItem(**{k: i[k] for k in ("sku", "name", "quantity", "unit_price")})
            for i in o["items"]
        ],
        payment_method=pay["method"],
        estimated_delivery=o["estimated_delivery"],
        delivered_at=o["delivered_at"],
        cancelled_at=o["cancelled_at"],
        delivery_address=Address(**o["delivery_address"]),
        shipment_id=o["shipment_id"],
    )
    when = (
        f"entregue em {o['delivered_at']}"
        if o["delivered_at"]
        else f"cancelado em {o['cancelled_at']}"
        if o["cancelled_at"]
        else f"previsão de entrega {o['estimated_delivery']}"
    )
    return ok(
        result,
        f"Pedido {o['id']} de {o['created_at']}: status {o['status']}, total {brl(o['total'])}, "
        f"{when}. Entrega em {fmt_address(o['delivery_address'])}.",
    )


def _shipment(o: dict) -> dict:
    if not o["shipment_id"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} ainda não foi enviado (status {o['status']}).",
            recoverable=False,
            suggested_tool="get_order_status",
        )
    return SHIPMENTS[o["shipment_id"]]


@catalog_tool(
    skill=SKILL,
    scope="orders:read",
    title="Rastrear entrega",
    annotations=READ,
    result=ShipmentResult,
    description="""
Rastreia a entrega de um pedido já enviado: transportadora, código de rastreio, previsão e \
eventos de movimentação.
WHEN TO USE: "cadê minha encomenda?", "onde está o pacote?", "qual o código de rastreio?", \
atraso na entrega.
DON'T USE FOR: status geral ou itens do pedido (use get_order_status); mudar endereço (use \
update_delivery_address) ou data de entrega (use reschedule_delivery).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: eventos em ordem cronológica; repasse códigos e datas sem alterar.
""",
    examples=[
        "Cadê minha encomenda?",
        "Qual o código de rastreio do pedido O0005?",
        "Meu pacote está parado na transportadora",
        "Onde está minha entrega agora?",
    ],
    keywords=["rastreio", "rastrear", "encomenda", "pacote", "transportadora", "cade", "correios"],
)
async def track_shipment(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    s = _shipment(o)
    result = ShipmentResult(
        order_id=o["id"],
        shipment_id=s["id"],
        carrier=s["carrier"],
        tracking_code=s["tracking_code"],
        shipment_status=s["status"],
        eta=s["eta"],
        events=[ShipmentEvent(**e) for e in s["events"]],
    )
    last = s["events"][-1]
    return ok(
        result,
        f"Pedido {o['id']} com {s['carrier']}, rastreio {s['tracking_code']}, status "
        f"{s['status']}, previsão {s['eta']}. Último evento em {last['at']}: "
        f"{last['description']} ({last['location']}).",
    )


@catalog_tool(
    skill=SKILL,
    scope="orders:write",
    title="Alterar endereço de entrega",
    annotations=WRITE,
    result=AddressUpdateResult,
    description="""
Altera o endereço de entrega de um pedido que ainda não foi enviado.
WHEN TO USE: o cliente quer receber em outro endereço ou corrigir o endereço de um pedido em \
preparação.
DON'T USE FOR: mudar a data de entrega (use reschedule_delivery); pedido já enviado (use \
escalate_to_human); alterar o cadastro.
PARAMETERS: só o endereço novo dito pelo cliente; nunca copie o atual. complement opcional; \
state = UF; postal_code = CEP de 8 dígitos.
CONFIRMATION: não requer.
RESULT: protocolo e endereço novo; repasse sem alterar.
""",
    examples=[
        "Quero mudar o endereço de entrega do meu pedido",
        "Errei o número da casa no pedido, é 250",
        "Posso receber no meu trabalho em vez de em casa?",
        "Troca o endereço do pedido O0003 para Rua Bahia, 90",
    ],
    keywords=["endereco", "mudar endereco", "alterar endereco", "entregar em outro lugar", "cep"],
)
async def update_delivery_address(
    street: Annotated[str, Field(description="Logradouro (rua, avenida)", max_length=120)],
    number: Annotated[str, Field(description="Número do imóvel", max_length=10)],
    neighborhood: Annotated[str, Field(description="Bairro", max_length=80)],
    city: Annotated[str, Field(description="Cidade", max_length=80)],
    state: Annotated[str, Field(description="UF com 2 letras (ex.: SP)", max_length=2)],
    postal_code: Annotated[str, Field(description="CEP com 8 dígitos", max_length=9)],
    order_id: OrderId = None,
    complement: Annotated[
        str | None, Field(description="Complemento (apto, bloco), se dito", max_length=60)
    ] = None,
) -> ToolResult:
    o = resolve_order(order_id)
    if o["status"] not in NOT_SHIPPED:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O endereço do pedido {o['id']} não pode mais ser alterado (status {o['status']}).",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    cep = re.sub(r"\D", "", postal_code)
    uf = state.strip().upper()
    if len(cep) != 8 or uf not in UFS:
        raise ToolFailure(
            "VALIDATION_ERROR",
            "CEP deve ter 8 dígitos e UF deve ser uma sigla válida.",
            recoverable=True,
        )
    new = Address(
        street=street.strip(),
        number=number.strip(),
        complement=complement,
        neighborhood=neighborhood.strip(),
        city=city.strip(),
        state=uf,
        postal_code=cep,
    )
    proto = protocol("END", "update_delivery_address", {"order_id": o["id"], **new.model_dump()})
    result = AddressUpdateResult(
        order_id=o["id"],
        protocol=proto,
        previous_address=Address(**o["delivery_address"]),
        new_address=new,
    )
    return ok(
        result, f"Endereço do pedido {o['id']} alterado para {fmt_address(new)}. Protocolo {proto}."
    )


@catalog_tool(
    skill=SKILL,
    scope="orders:write",
    title="Reagendar entrega",
    annotations=WRITE,
    result=RescheduleResult,
    description="""
Reagenda a entrega de um pedido já enviado e ainda não entregue para uma nova data e período.
WHEN TO USE: o cliente não estará em casa, quer receber em outro dia ou perdeu a tentativa de \
entrega.
DON'T USE FOR: trocar o endereço (use update_delivery_address); saber onde está o pacote (use \
track_shipment); desistir do pedido (use cancel_order).
PARAMETERS: new_date em AAAA-MM-DD, de 1 a 15 dias à frente; period = manha | tarde | comercial.
CONFIRMATION: não requer.
RESULT: protocolo e nova janela de entrega; repasse sem alterar.
""",
    examples=[
        "Não vou estar em casa amanhã, dá para entregar outro dia?",
        "O entregador veio e eu não estava, quero reagendar",
        "Pode entregar o pedido na sexta à tarde?",
        "Quero remarcar a entrega para semana que vem",
    ],
    keywords=["reagendar", "remarcar", "outro dia", "nao estarei em casa", "tentativa de entrega"],
)
async def reschedule_delivery(
    new_date: Annotated[str, Field(description="Nova data de entrega, AAAA-MM-DD")],
    order_id: OrderId = None,
    period: Annotated[
        Literal["manha", "tarde", "comercial"],
        Field(description="Janela: manha (8-12h), tarde (13-18h) ou comercial (8-18h)"),
    ] = "comercial",
) -> ToolResult:
    o = resolve_order(order_id)
    s = _shipment(o)
    if s["status"] == "delivered":
        raise ToolFailure("NOT_ELIGIBLE", f"O pedido {o['id']} já foi entregue.", recoverable=False)
    if s["status"] == "lost":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A entrega do pedido {o['id']} foi extraviada e não pode ser reagendada.",
            recoverable=False,
            suggested_tool=money_back_next_step(o),
        )
    try:
        wanted = date.fromisoformat(new_date.strip())
    except ValueError:
        wanted = None
    if wanted is None or not 1 <= (wanted - TODAY).days <= 15:
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"new_date deve estar no formato AAAA-MM-DD, entre 1 e 15 dias após {TODAY}.",
            recoverable=True,
        )
    proto = protocol(
        "AGD",
        "reschedule_delivery",
        {"order_id": o["id"], "new_date": wanted.isoformat(), "period": period},
    )
    result = RescheduleResult(
        order_id=o["id"],
        protocol=proto,
        shipment_id=s["id"],
        new_date=wanted.isoformat(),
        period=period,
    )
    return ok(
        result,
        f"Entrega do pedido {o['id']} reagendada para {wanted.isoformat()}, "
        f"período {period}. Protocolo {proto}.",
    )


@catalog_tool(
    skill=SKILL,
    scope="orders:cancel",
    title="Cancelar pedido",
    annotations=DESTRUCTIVE,
    result=CancellationResult,
    description="""
Cancela um pedido que ainda não foi enviado; o estorno do pagamento é automático. Irreversível.
WHEN TO USE: "quero cancelar meu pedido", desistência antes do envio.
DON'T USE FOR: pedido já entregue (use create_return_request); dinheiro de volta de pedido já \
cancelado ou extraviado (use request_refund); cobrança não reconhecida (use dispute_charge).
PARAMETERS: order_id opcional se o cliente tem um só pedido; reason opcional.
CONFIRMATION: o servidor não pede confirmação; a ação é irreversível.
RESULT: protocolo, valor e prazo do estorno; repasse sem alterar.
""",
    examples=[
        "Não quero mais a compra, podem cancelar?",
        "Desisti da compra, cancela o O0004 por favor",
        "Comprei errado, dá para cancelar antes de enviar?",
        "Cancela a compra que fiz ontem",
    ],
    keywords=["cancelar", "cancelamento", "desistir", "anular compra", "nao quero mais"],
)
async def cancel_order(
    order_id: OrderId = None,
    reason: Annotated[
        str | None, Field(description="Motivo dito pelo cliente, se houver", max_length=300)
    ] = None,
) -> ToolResult:
    o = resolve_order(order_id)
    if o["status"] == "cancelled":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} já está cancelado.",
            recoverable=False,
            suggested_tool=money_back_next_step(o),
        )
    if o["status"] == "delivered":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} já foi entregue e não pode ser cancelado; abra uma devolução.",
            recoverable=False,
            suggested_tool=after_delivery_next_step(o),
        )
    if o["status"] not in NOT_SHIPPED:
        lost = SHIPMENTS[o["shipment_id"]]["status"] == "lost" if o["shipment_id"] else False
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} já foi enviado e não pode ser cancelado; recuse a entrega "
            "ou abra uma devolução após o recebimento.",
            recoverable=False,
            suggested_tool=money_back_next_step(o) if lost else "escalate_to_human",
        )
    pay = PAYMENTS[o["payment_id"]]
    paid = pay["status"] == "approved"
    refund = Money(**o["total"]) if paid else Money(amount=0.0)
    method = pay["method"] if paid else "sem_cobranca"
    deadline = refund_deadline(pay["method"]) if paid else TODAY.isoformat()
    proto = protocol("CAN", "cancel_order", {"order_id": o["id"], "reason": reason})
    result = CancellationResult(
        order_id=o["id"],
        protocol=proto,
        cancelled_at=TODAY.isoformat(),
        refund_amount=refund,
        refund_method=method,
        refund_deadline=deadline,
    )
    refund_text = (
        f"Estorno de {brl(refund)}: {REFUND_TEXT[pay['method']]} (até {deadline})."
        if paid
        else "Não houve cobrança, então não há estorno."
    )
    return ok(result, f"Pedido {o['id']} cancelado. Protocolo {proto}. {refund_text}")
