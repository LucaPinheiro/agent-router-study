"""Skill assistencia_tecnica: schedule_installation, request_technical_visit,
reschedule_technical_visit, get_service_order_status, cancel_service_order,
check_extended_warranty."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    DESTRUCTIVE,
    READ,
    TODAY,
    WRITE,
    ToolFailure,
    ok,
    pick_sku,
    protocol,
    resolve_order,
)
from mcp_server.large.data import (
    EXT_WARRANTY_BY_ORDER,
    SERVICE_ORDERS,
    W,
    days_since,
    future_date,
    large_tool,
    resolve_service_order,
)
from mcp_server.large.models import (
    ExtendedWarrantyResult,
    ServiceOrderCancelResult,
    ServiceOrderResult,
)

SKILL = "assistencia_tecnica"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]
Sku = Annotated[str | None, Field(description="SKU do item. Omita se o pedido tem um só item")]
ServiceOrderId = Annotated[
    str | None,
    Field(description="Ordem de serviço (ex.: OS-1A2B3C4D). Omita se o cliente tem uma só"),
]
Period = Annotated[
    Literal["manha", "tarde", "comercial"],
    Field(description="Janela: manha (8-12h), tarde (13-18h) ou comercial (8-18h)"),
]
SERVICE_CATEGORIES = ("eletrodomesticos",)
OPEN = ("agendada", "em_atendimento")


def _delivered_item(order_id: str | None, sku: str | None) -> tuple[dict, dict]:
    o = resolve_order(order_id)
    if not o["delivered_at"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} ainda não foi entregue (status {o['status']}).",
            recoverable=False,
            suggested_tool="track_shipment" if o["shipment_id"] else "get_order_status",
        )
    return o, pick_sku(o, sku)


def _open_service(order_id: str) -> dict | None:
    return next(
        (s for s in SERVICE_ORDERS.values() if s["order_id"] == order_id and s["status"] in OPEN),
        None,
    )


def _service_result(s: dict) -> ServiceOrderResult:
    return ServiceOrderResult(
        service_order_id=s["id"],
        order_id=s["order_id"],
        sku=s["sku"],
        type=s["type"],
        service_status=s["status"],
        scheduled_for=s["scheduled_for"],
        period=s["period"],
        technician=s["technician"],
    )


def _new_service(
    kind: str, prefix: str, o: dict, item: dict, when: date, period: str, extra: dict
) -> ServiceOrderResult:
    sid = protocol(
        prefix,
        kind,
        {
            "order_id": o["id"],
            "sku": item["sku"],
            "date": when.isoformat(),
            "period": period,
            **extra,
        },
    )
    return ServiceOrderResult(
        service_order_id=sid,
        order_id=o["id"],
        sku=item["sku"],
        type="instalacao" if kind == "schedule_installation" else "visita_tecnica",
        service_status="agendada",
        scheduled_for=when.isoformat(),
        period=period,
        technician="Técnico credenciado Assist+",
    )


@large_tool(
    skill=SKILL,
    scope="services:write",
    title="Agendar instalação",
    annotations=WRITE,
    result=ServiceOrderResult,
    description="""
Agenda a instalação gratuita, por técnico credenciado, de um eletrodoméstico já entregue.
WHEN TO USE: "quero marcar a instalação da cafeteira", "preciso de alguém para instalar o \
aparelho que chegou".
DON'T USE FOR: produto com defeito (use request_technical_visit); remarcar uma instalação já \
agendada (use reschedule_technical_visit); data de entrega do pedido (use reschedule_delivery).
PARAMETERS: date em AAAA-MM-DD, de 1 a 15 dias à frente; period = manha | tarde | comercial; \
sku opcional se o pedido tem um só item.
CONFIRMATION: não requer.
RESULT: número da ordem de serviço (OS), data e período; repasse sem alterar.
""",
    examples=[
        "Quero marcar a instalação da cafeteira que chegou ontem",
        "Vocês mandam alguém montar e instalar o eletrodoméstico?",
        "Dá para agendar a instalação para sábado de manhã?",
        "O aparelho chegou, como faço para ter a instalação gratuita?",
    ],
    keywords=["instalacao", "instalar", "montagem", "tecnico", "agendar instalacao"],
)
async def schedule_installation(
    date: Annotated[str, Field(description="Data da instalação, AAAA-MM-DD")],
    order_id: OrderId = None,
    sku: Sku = None,
    period: Period = "comercial",
) -> ToolResult:
    o, item = _delivered_item(order_id, sku)
    if item["category"] not in SERVICE_CATEGORIES:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"{item['name']} não tem instalação; o serviço vale só para eletrodomésticos.",
            recoverable=False,
        )
    if (s := _open_service(o["id"])) is not None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Já existe a ordem de serviço {s['id']} ({s['type']}, {s['status']}) para o pedido "
            f"{o['id']}.",
            recoverable=False,
            suggested_tool="get_service_order_status",
        )
    when = future_date(
        date, W["service_schedule_min_days_ahead"], W["service_schedule_max_days_ahead"]
    )
    result = _new_service("schedule_installation", "OS", o, item, when, period, {})
    return ok(
        result,
        f"Instalação de {item['name']} (pedido {o['id']}) agendada para {when.isoformat()}, "
        f"período {period}. Ordem de serviço {result.service_order_id}.",
    )


@large_tool(
    skill=SKILL,
    scope="services:write",
    title="Solicitar visita técnica",
    annotations=WRITE,
    result=ServiceOrderResult,
    description="""
Abre uma visita técnica em casa para eletrodoméstico com defeito, coberto pela garantia de 12 \
meses ou por garantia estendida ativa.
WHEN TO USE: "a geladeira/cafeteira parou e quero um técnico em casa", defeito em \
eletrodoméstico instalado.
DON'T USE FOR: produto portátil com defeito, enviado para análise (use open_warranty_claim); \
só consultar a cobertura (use check_extended_warranty); instalação de produto novo (use \
schedule_installation).
PARAMETERS: problem_description = defeito nas palavras do cliente; date em AAAA-MM-DD, de 1 a \
15 dias à frente; period opcional; sku opcional se o pedido tem um só item.
CONFIRMATION: não requer.
RESULT: número da OS, data e período; repasse sem alterar.
""",
    examples=[
        "O liquidificador parou de girar, quero um técnico em casa",
        "Preciso de uma visita técnica para a cafeteira que está vazando",
        "Meu eletrodoméstico deu problema, vocês mandam assistência em domicílio?",
        "Quero que um técnico venha ver o aparelho que não liga",
    ],
    keywords=["visita tecnica", "tecnico", "assistencia", "conserto em casa", "reparo"],
)
async def request_technical_visit(
    problem_description: Annotated[
        str, Field(description="Defeito nas palavras do cliente", max_length=500)
    ],
    date: Annotated[str, Field(description="Data desejada para a visita, AAAA-MM-DD")],
    order_id: OrderId = None,
    sku: Sku = None,
    period: Period = "comercial",
) -> ToolResult:
    o, item = _delivered_item(order_id, sku)
    days = days_since(o["delivered_at"])
    plan = EXT_WARRANTY_BY_ORDER.get(o["id"])
    if item["category"] not in SERVICE_CATEGORIES:
        warranty = (
            W["return_or_exchange_days_after_delivery"] < days <= W["warranty_days_after_delivery"]
        )
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Visita técnica vale só para eletrodomésticos; {item['name']} é analisado pela "
            "garantia com envio do produto.",
            recoverable=False,
            suggested_tool="open_warranty_claim" if warranty else "check_extended_warranty",
        )
    covered = days <= W["warranty_days_after_delivery"] or (
        plan is not None and plan["status"] == "ativa" and TODAY.isoformat() <= plan["valid_until"]
    )
    if not covered:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"{item['name']} do pedido {o['id']} está fora da garantia e sem garantia estendida "
            "ativa.",
            recoverable=False,
            suggested_tool="check_extended_warranty",
        )
    if (s := _open_service(o["id"])) is not None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Já existe a ordem de serviço {s['id']} ({s['type']}, {s['status']}) para o pedido "
            f"{o['id']}.",
            recoverable=False,
            suggested_tool="get_service_order_status",
        )
    when = future_date(
        date, W["service_schedule_min_days_ahead"], W["service_schedule_max_days_ahead"]
    )
    result = _new_service(
        "request_technical_visit", "OS", o, item, when, period, {"problem": problem_description}
    )
    return ok(
        result,
        f"Visita técnica para {item['name']} (pedido {o['id']}) agendada para "
        f"{when.isoformat()}, período {period}. Ordem de serviço {result.service_order_id}.",
    )


@large_tool(
    skill=SKILL,
    scope="services:write",
    title="Reagendar visita técnica",
    annotations=WRITE,
    result=ServiceOrderResult,
    description="""
Remarca a data ou o período de uma instalação ou visita técnica já agendada.
WHEN TO USE: "não vou estar em casa no dia do técnico", "quero mudar o dia da instalação".
DON'T USE FOR: data de entrega de um pedido (use reschedule_delivery); data da próxima entrega \
da assinatura (use change_subscription_date); desistir do atendimento (use \
cancel_service_order).
PARAMETERS: new_date em AAAA-MM-DD, de 1 a 15 dias à frente; period opcional; \
service_order_id opcional se o cliente tem uma só OS.
CONFIRMATION: não requer.
RESULT: OS com a nova data e período; repasse sem alterar.
""",
    examples=[
        "Não vou estar em casa no dia que o técnico vem, dá para mudar?",
        "Quero passar a instalação para a semana que vem",
        "Pode remarcar a visita técnica para a tarde?",
        "Preciso trocar o dia do atendimento técnico",
    ],
    keywords=["remarcar visita", "reagendar tecnico", "mudar dia instalacao", "outro horario"],
)
async def reschedule_technical_visit(
    new_date: Annotated[str, Field(description="Nova data, AAAA-MM-DD")],
    service_order_id: ServiceOrderId = None,
    period: Period = "comercial",
) -> ToolResult:
    s = resolve_service_order(service_order_id)
    if s["status"] != "agendada":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A ordem de serviço {s['id']} está {s['status']} e não pode ser remarcada.",
            recoverable=False,
            suggested_tool="get_service_order_status",
        )
    when = future_date(
        new_date, W["service_schedule_min_days_ahead"], W["service_schedule_max_days_ahead"]
    )
    proto = protocol(
        "AGT",
        "reschedule_technical_visit",
        {"id": s["id"], "date": when.isoformat(), "period": period},
    )
    result = ServiceOrderResult(
        **{
            **_service_result(s).model_dump(exclude={"status"}),
            "scheduled_for": when.isoformat(),
            "period": period,
        }
    )
    return ok(
        result,
        f"Ordem de serviço {s['id']} remarcada para {when.isoformat()}, período {period}. "
        f"Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="services:read",
    title="Status da ordem de serviço",
    annotations=READ,
    result=ServiceOrderResult,
    description="""
Consulta uma ordem de serviço de instalação ou visita técnica: status, data, período e técnico.
WHEN TO USE: "o técnico vem que dia?", "como está minha ordem de serviço?", acompanhar \
instalação ou visita.
DON'T USE FOR: situação de um pedido ou entrega (use get_order_status); reembolso (use \
get_refund_status); outros protocolos de atendimento (use check_protocol_status).
PARAMETERS: service_order_id opcional se o cliente tem uma só OS; nunca invente o número.
CONFIRMATION: não requer.
RESULT: dados da OS; repasse datas e IDs sem alterar.
""",
    examples=[
        "Que dia o técnico vem aqui em casa?",
        "Como está a minha ordem de serviço da instalação?",
        "A visita técnica já foi confirmada?",
        "Quero acompanhar o atendimento técnico que pedi",
    ],
    keywords=["ordem de servico", "os", "tecnico vem", "status instalacao", "visita"],
)
async def get_service_order_status(service_order_id: ServiceOrderId = None) -> ToolResult:
    s = resolve_service_order(service_order_id)
    result = _service_result(s)
    return ok(
        result,
        f"Ordem de serviço {s['id']} ({s['type']}) do pedido {s['order_id']}: {s['status']}, "
        f"{s['scheduled_for']}, período {s['period']}.",
    )


@large_tool(
    skill=SKILL,
    scope="services:cancel",
    title="Cancelar ordem de serviço",
    annotations=DESTRUCTIVE,
    result=ServiceOrderCancelResult,
    description="""
Cancela uma instalação ou visita técnica agendada. Irreversível: um novo atendimento exige \
nova OS.
WHEN TO USE: "não preciso mais do técnico", "pode cancelar a instalação".
DON'T USE FOR: desistir de um pedido (use cancel_order); cancelar uma assinatura (use \
cancel_subscription); mudar o dia do técnico (use reschedule_technical_visit).
PARAMETERS: service_order_id opcional se o cliente tem uma só OS; reason opcional.
CONFIRMATION: o servidor não pede confirmação; a ação é irreversível.
RESULT: protocolo do cancelamento; repasse sem alterar.
""",
    examples=[
        "Não preciso mais do técnico, pode cancelar",
        "Quero desmarcar a instalação que agendei",
        "Cancela a visita técnica, o aparelho voltou a funcionar",
        "Desisti da instalação, podem cancelar a OS",
    ],
    keywords=["cancelar visita", "cancelar instalacao", "desmarcar tecnico", "cancelar os"],
)
async def cancel_service_order(
    service_order_id: ServiceOrderId = None,
    reason: Annotated[
        str | None, Field(description="Motivo dito pelo cliente, se houver", max_length=300)
    ] = None,
) -> ToolResult:
    s = resolve_service_order(service_order_id)
    if s["status"] != "agendada":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A ordem de serviço {s['id']} está {s['status']} e não pode ser cancelada.",
            recoverable=False,
            suggested_tool="get_service_order_status",
        )
    proto = protocol("CNS", "cancel_service_order", {"id": s["id"], "reason": reason})
    result = ServiceOrderCancelResult(
        service_order_id=s["id"], protocol=proto, cancelled_at=TODAY.isoformat()
    )
    return ok(result, f"Ordem de serviço {s['id']} cancelada. Protocolo {proto}.")


@large_tool(
    skill=SKILL,
    scope="services:read",
    title="Consultar garantia estendida",
    annotations=READ,
    result=ExtendedWarrantyResult,
    description="""
Consulta a cobertura de garantia de um item entregue: fim da garantia legal de 12 meses e, se \
houver, o plano de garantia estendida (validade e cobertura).
WHEN TO USE: "meu produto tem garantia estendida?", "até quando vai a garantia?", antes de \
pedir conserto de item antigo.
DON'T USE FOR: abrir o conserto (use request_technical_visit ou open_warranty_claim); prazo de \
devolução ou troca (use check_return_eligibility).
PARAMETERS: order_id opcional se o cliente tem um só pedido; sku opcional se o pedido tem um \
só item.
CONFIRMATION: não requer.
RESULT: datas de garantia e plano; repasse sem alterar.
""",
    examples=[
        "Meu smartwatch tem garantia estendida?",
        "Até quando vai a garantia do que eu comprei?",
        "Contratei a garantia estendida, ela já está valendo?",
        "Quero saber a cobertura do meu plano de garantia",
    ],
    keywords=["garantia estendida", "cobertura", "validade da garantia", "plano de garantia"],
)
async def check_extended_warranty(order_id: OrderId = None, sku: Sku = None) -> ToolResult:
    o, item = _delivered_item(order_id, sku)
    legal = (
        date.fromisoformat(o["delivered_at"]) + timedelta(days=W["warranty_days_after_delivery"])
    ).isoformat()
    plan = EXT_WARRANTY_BY_ORDER.get(o["id"])
    result = ExtendedWarrantyResult(
        order_id=o["id"],
        sku=item["sku"],
        legal_warranty_until=legal,
        has_extended_warranty=plan is not None,
        extended_warranty_id=plan["id"] if plan else None,
        plan_months=plan["plan_months"] if plan else None,
        extended_status=plan["status"] if plan else None,
        valid_until=plan["valid_until"] if plan else None,
        coverage=plan["coverage"] if plan else None,
    )
    text = f"{item['name']} (pedido {o['id']}): garantia legal até {legal}."
    if plan:
        text += (
            f" Garantia estendida {plan['id']} de {plan['plan_months']} meses, status "
            f"{plan['status']}, válida até {plan['valid_until']}."
        )
    else:
        text += " Sem garantia estendida contratada."
    return ok(result, text)
