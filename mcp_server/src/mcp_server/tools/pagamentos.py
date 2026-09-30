"""Skill pagamentos_reembolsos: get_payment_status, generate_boleto_second_copy, request_refund,
get_refund_status, dispute_charge."""

import hashlib
from datetime import date
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    DESTRUCTIVE,
    PAYMENTS,
    POLICIES,
    READ,
    REFUND_TEXT,
    REFUNDS_BY_ORDER,
    SHIPMENTS,
    TODAY,
    WRITE,
    ToolFailure,
    brl,
    catalog_tool,
    days_from_today,
    ensure_no_money_back,
    money_back_next_step,
    ok,
    protocol,
    refund_deadline,
    resolve_order,
)
from mcp_server.models import (
    BoletoResult,
    DisputeResult,
    Money,
    PaymentStatusResult,
    RefundRequestResult,
    RefundStatusResult,
)

SKILL = "pagamentos_reembolsos"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]


@catalog_tool(
    skill=SKILL,
    scope="payments:read",
    title="Status do pagamento",
    annotations=READ,
    result=PaymentStatusResult,
    description="""
Consulta o pagamento de um pedido: forma, status (pendente, aprovado, estornado, contestado), \
valor, parcelas e vencimento do boleto.
WHEN TO USE: "meu pagamento foi aprovado?", "o boleto já compensou?", "em quantas parcelas ficou?".
DON'T USE FOR: dinheiro que deve voltar ao cliente (use get_refund_status); emitir boleto novo \
(use generate_boleto_second_copy); status do pedido (use get_order_status).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: dados do pagamento; repasse valores e datas sem alterar.
""",
    examples=[
        "Meu pagamento foi aprovado?",
        "O boleto que paguei já compensou?",
        "Em quantas parcelas ficou minha compra?",
        "Por que meu pedido ainda está aguardando pagamento?",
    ],
    keywords=["pagamento", "aprovado", "compensou", "parcelas", "cobranca", "pago"],
)
async def get_payment_status(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    p = PAYMENTS[o["payment_id"]]
    result = PaymentStatusResult(
        order_id=o["id"],
        payment_id=p["id"],
        method=p["method"],
        payment_status=p["status"],
        amount=Money(**p["amount"]),
        installments=p["installments"],
        paid_at=p["paid_at"],
        boleto_due_date=p["boleto_due_date"],
    )
    extra = f", pago em {p['paid_at']}" if p["paid_at"] else ""
    if p["boleto_due_date"] and p["status"] == "pending":
        extra += f", boleto com vencimento em {p['boleto_due_date']}"
    return ok(
        result,
        f"Pagamento {p['id']} do pedido {o['id']}: {p['method']}, status {p['status']}, "
        f"{brl(p['amount'])} em {p['installments']}x{extra}.",
    )


@catalog_tool(
    skill=SKILL,
    scope="payments:write",
    title="2ª via do boleto",
    annotations=WRITE,
    result=BoletoResult,
    description="""
Emite a 2ª via do boleto de um pedido com pagamento pendente, com novo vencimento.
WHEN TO USE: "preciso da 2ª via do boleto", boleto vencido ou perdido.
DON'T USE FOR: saber se o boleto já foi pago (use get_payment_status); pedidos pagos com \
cartão ou Pix.
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: linha digitável, valor e vencimento; repasse sem alterar nenhum dígito.
""",
    examples=[
        "Pode reemitir o boleto da minha compra?",
        "Meu boleto venceu, como pago agora?",
        "Perdi o boleto do pedido O0001",
        "Gera um boleto novo para mim",
    ],
    keywords=["boleto", "segunda via", "2a via", "vencido", "linha digitavel", "codigo de barras"],
)
async def generate_boleto_second_copy(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    p = PAYMENTS[o["payment_id"]]
    if p["method"] != "boleto":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} foi pago com {p['method']}, não com boleto.",
            recoverable=False,
            suggested_tool="get_payment_status",
        )
    if p["status"] != "pending":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O boleto do pedido {o['id']} já foi pago (status {p['status']}).",
            recoverable=False,
            suggested_tool="get_payment_status",
        )
    due = days_from_today(POLICIES["windows"]["boleto_second_copy_due_days"])
    digest = hashlib.sha256(f"{p['id']}|{due}".encode()).hexdigest()
    barcode = str(int(digest, 16))[:47]
    result = BoletoResult(
        order_id=o["id"],
        payment_id=p["id"],
        barcode=barcode,
        amount=Money(**p["amount"]),
        due_date=due,
    )
    return ok(
        result,
        f"2ª via do boleto do pedido {o['id']}: {brl(p['amount'])}, vencimento "
        f"{due}. Linha digitável: {barcode}.",
    )


@catalog_tool(
    skill=SKILL,
    scope="payments:refund",
    title="Solicitar reembolso",
    annotations=WRITE,
    result=RefundRequestResult,
    description="""
Solicita o reembolso de um pedido cancelado que não foi estornado ou extraviado na entrega.
WHEN TO USE: "quero meu dinheiro de volta" de pedido cancelado sem estorno ou que nunca chegou \
(extraviado).
DON'T USE FOR: se o pedido ainda não foi enviado (use cancel_order); produto recebido a \
devolver (use create_return_request); acompanhar reembolso já pedido (use get_refund_status); \
cobrança não reconhecida (use dispute_charge).
PARAMETERS: order_id opcional se o cliente tem um só pedido; reason = motivo curto.
CONFIRMATION: não requer.
RESULT: id do reembolso, valor e prazo; repasse sem alterar.
""",
    examples=[
        "Quero meu dinheiro de volta, o pedido foi cancelado e não estornaram",
        "Meu pedido foi extraviado, quero o reembolso",
        "O pedido nunca chegou, quero ser reembolsado",
        "Cancelaram minha compra e o valor não voltou",
    ],
    keywords=["reembolso", "dinheiro de volta", "estorno", "extraviado", "ressarcimento"],
)
async def request_refund(
    reason: Annotated[str, Field(description="Motivo curto dito pelo cliente", max_length=300)],
    order_id: OrderId = None,
) -> ToolResult:
    o = resolve_order(order_id)
    p = PAYMENTS[o["payment_id"]]
    if o["id"] in REFUNDS_BY_ORDER or p["status"] == "refunded":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Já existe reembolso para o pedido {o['id']}.",
            recoverable=False,
            suggested_tool="get_refund_status",
        )
    if p["status"] != "approved":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pagamento do pedido {o['id']} está com status {p['status']}; não há valor a "
            "reembolsar.",
            recoverable=False,
            suggested_tool="get_payment_status",
        )
    lost = bool(o["shipment_id"]) and SHIPMENTS[o["shipment_id"]]["status"] == "lost"
    if not (o["status"] == "cancelled" or lost):
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} (status {o['status']}) não está cancelado nem extraviado.",
            recoverable=False,
            suggested_tool=money_back_next_step(o),
        )
    refund_id = protocol("REF", "request_refund", {"order_id": o["id"], "reason": reason})
    deadline = refund_deadline(p["method"])
    result = RefundRequestResult(
        order_id=o["id"],
        refund_id=refund_id,
        amount=Money(**p["amount"]),
        method=p["method"],
        expected_by=deadline,
    )
    return ok(
        result,
        f"Reembolso {refund_id} de {brl(p['amount'])} solicitado para o pedido "
        f"{o['id']}: {REFUND_TEXT[p['method']]} (até {deadline}).",
    )


@catalog_tool(
    skill=SKILL,
    scope="payments:read",
    title="Status do reembolso",
    annotations=READ,
    result=RefundStatusResult,
    description="""
Consulta um reembolso já solicitado: status, valor, forma de devolução e prazo previsto.
WHEN TO USE: "meu reembolso já caiu?", "quando recebo o estorno?".
DON'T USE FOR: situação do pagamento original (use get_payment_status); pedir um reembolso \
novo (use request_refund).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: status e prazo do reembolso; repasse sem alterar.
""",
    examples=[
        "Meu reembolso já caiu?",
        "Quando o estorno vai aparecer na fatura?",
        "Cadê o dinheiro do pedido que cancelei?",
        "Qual o prazo do meu reembolso?",
    ],
    keywords=["reembolso", "estorno", "caiu", "prazo do reembolso", "devolucao do dinheiro"],
)
async def get_refund_status(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    r = REFUNDS_BY_ORDER.get(o["id"])
    if r is None:
        raise ToolFailure(
            "NOT_FOUND",
            f"Não há reembolso registrado para o pedido {o['id']}.",
            recoverable=False,
            suggested_tool=money_back_next_step(o),
        )
    result = RefundStatusResult(
        order_id=o["id"],
        refund_id=r["id"],
        refund_status=r["status"],
        amount=Money(**r["amount"]),
        method=r["method"],
        requested_at=r["requested_at"],
        expected_by=r["expected_by"],
    )
    return ok(
        result,
        f"Reembolso {r['id']} do pedido {o['id']}: status {r['status']}, "
        f"{brl(r['amount'])}, {REFUND_TEXT[r['method']]} (até {r['expected_by']}).",
    )


@catalog_tool(
    skill=SKILL,
    scope="payments:dispute",
    title="Contestar cobrança",
    annotations=DESTRUCTIVE,
    result=DisputeResult,
    description="""
Abre contestação (chargeback) de cobrança no cartão de crédito: não reconhecida, duplicada ou \
com valor divergente. Irreversível.
WHEN TO USE: "não reconheço essa cobrança", "fui cobrado duas vezes", valor cobrado diferente.
DON'T USE FOR: desistência ou devolução (use cancel_order, request_refund ou \
create_return_request); pagamento por Pix ou boleto.
PARAMETERS: reason = nao_reconhecida | duplicada | valor_divergente; details opcional.
CONFIRMATION: o servidor não pede confirmação; a ação é irreversível.
RESULT: id da contestação e prazo; repasse sem alterar.
""",
    examples=[
        "Não reconheço essa cobrança no meu cartão",
        "Fui cobrado duas vezes pela mesma compra",
        "O valor cobrado na fatura é maior que o do pedido",
        "Quero contestar uma compra no cartão",
    ],
    keywords=["contestar", "chargeback", "nao reconheco", "cobrado duas vezes", "fatura"],
)
async def dispute_charge(
    reason: Annotated[
        Literal["nao_reconhecida", "duplicada", "valor_divergente"],
        Field(description="Tipo de contestação"),
    ],
    order_id: OrderId = None,
    details: Annotated[
        str | None, Field(description="Detalhes ditos pelo cliente, se houver", max_length=500)
    ] = None,
) -> ToolResult:
    o = resolve_order(order_id)
    p = PAYMENTS[o["payment_id"]]
    if p["method"] != "credit_card":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Contestação só vale para cartão de crédito; o pedido {o['id']} foi pago com "
            f"{p['method']}.",
            recoverable=False,
            suggested_tool=nxt
            if (nxt := money_back_next_step(o)) in ("request_refund", "get_refund_status")
            else "escalate_to_human",
        )
    ensure_no_money_back(o)
    if p["status"] in ("chargeback", "refunded"):
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pagamento do pedido {o['id']} já está com status {p['status']}.",
            recoverable=False,
            suggested_tool="get_payment_status",
        )
    max_days = POLICIES["windows"]["dispute_max_days_after_payment"]
    if (TODAY - date.fromisoformat(p["paid_at"])).days > max_days:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A cobrança do pedido {o['id']} tem mais de {max_days} dias e não pode ser "
            "contestada.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    dispute_id = protocol(
        "CTS", "dispute_charge", {"order_id": o["id"], "reason": reason, "details": details}
    )
    until = days_from_today(POLICIES["sla"]["dispute_resolution_days"])
    result = DisputeResult(
        order_id=o["id"],
        dispute_id=dispute_id,
        payment_id=p["id"],
        amount=Money(**p["amount"]),
        reason=reason,
        expected_resolution_by=until,
    )
    return ok(
        result,
        f"Contestação {dispute_id} aberta para a cobrança de {brl(p['amount'])} "
        f"do pedido {o['id']} (motivo {reason}). Resposta até {until}.",
    )
