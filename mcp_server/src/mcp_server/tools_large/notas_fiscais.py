"""Skill notas_fiscais_cadastro: get_invoice, resend_invoice, request_invoice_correction,
issue_return_invoice, get_purchase_receipt, update_billing_data."""

import hashlib
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    PAYMENTS,
    READ,
    WRITE,
    ToolFailure,
    after_delivery_next_step,
    brl,
    days_from_today,
    get_customer,
    ok,
    pick_sku,
    protocol,
    resolve_order,
)
from mcp_server.large.data import (
    BILLING,
    INVOICES_BY_ORDER,
    SLA,
    W,
    days_since,
    large_tool,
    mask_email,
)
from mcp_server.large.models import (
    BillingUpdateResult,
    InvoiceCorrectionResult,
    InvoiceResendResult,
    InvoiceResult,
    PurchaseReceiptResult,
    ReturnInvoiceResult,
)
from mcp_server.models import Money

SKILL = "notas_fiscais_cadastro"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]


def _invoice(order_id: str | None) -> tuple[dict, dict]:
    o = resolve_order(order_id)
    nf = INVOICES_BY_ORDER.get(o["id"])
    if nf is None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A nota fiscal do pedido {o['id']} ainda não foi emitida (status {o['status']}); "
            "ela sai no despacho.",
            recoverable=False,
            suggested_tool="get_order_status",
        )
    return o, nf


@large_tool(
    skill=SKILL,
    scope="invoices:read",
    title="Consultar nota fiscal",
    annotations=READ,
    result=InvoiceResult,
    description="""
Consulta a nota fiscal (NF-e) de um pedido: número, série, data de emissão, chave de acesso, \
valor e dados do destinatário.
WHEN TO USE: "preciso da nota fiscal da compra", "qual a chave de acesso da NF?", "a nota já \
foi emitida?".
DON'T USE FOR: comprovante de pagamento (use get_purchase_receipt); status do pagamento (use \
get_payment_status); receber a nota por e-mail de novo (use resend_invoice).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: dados da NF-e; repasse a chave de acesso sem alterar nenhum dígito.
""",
    examples=[
        "Preciso do número da nota fiscal da minha compra",
        "Qual a chave de acesso da NF do pedido?",
        "A nota fiscal já foi emitida?",
        "Onde vejo a DANFE do que eu comprei?",
    ],
    keywords=["nota fiscal", "nf", "nfe", "danfe", "chave de acesso", "xml"],
)
async def get_invoice(order_id: OrderId = None) -> ToolResult:
    o, nf = _invoice(order_id)
    b = BILLING[o["customer_id"]]
    result = InvoiceResult(
        order_id=o["id"],
        invoice_number=nf["number"],
        series=nf["series"],
        issued_at=nf["issued_at"],
        access_key=nf["access_key"],
        amount=Money(**nf["amount"]),
        billing_name=b["billing_name"],
        doc_masked=b["doc_masked"],
    )
    return ok(
        result,
        f"NF-e {nf['number']} série {nf['series']} do pedido {o['id']}, emitida em "
        f"{nf['issued_at']}, {brl(nf['amount'])}, para {b['billing_name']}. Chave de acesso: "
        f"{nf['access_key']}.",
    )


@large_tool(
    skill=SKILL,
    scope="invoices:write",
    title="Reenviar nota fiscal",
    annotations=WRITE,
    result=InvoiceResendResult,
    description="""
Reenvia o PDF e o XML da nota fiscal de um pedido para o e-mail ou WhatsApp cadastrado.
WHEN TO USE: "não recebi a nota fiscal", "manda a NF de novo para o meu e-mail".
DON'T USE FOR: corrigir dados da nota (use request_invoice_correction); trocar o e-mail do \
cadastro (use update_contact_info).
PARAMETERS: channel = email | whatsapp (padrão email); order_id opcional se o cliente tem um \
só pedido.
CONFIRMATION: não requer.
RESULT: protocolo e destino mascarado; repasse sem alterar.
""",
    examples=[
        "Não recebi a nota fiscal no meu e-mail",
        "Manda o XML da nota de novo, por favor",
        "Pode reenviar a NF pelo WhatsApp?",
        "Perdi o e-mail com a nota, envia outra vez",
    ],
    keywords=["reenviar nota", "nao recebi a nota", "mandar nf", "xml", "pdf da nota"],
)
async def resend_invoice(
    order_id: OrderId = None,
    channel: Annotated[Literal["email", "whatsapp"], Field(description="Canal de envio")] = "email",
) -> ToolResult:
    o, nf = _invoice(order_id)
    c = get_customer()
    dest = mask_email(c["email"]) if channel == "email" else "WhatsApp cadastrado"
    proto = protocol("ENF", "resend_invoice", {"order_id": o["id"], "channel": channel})
    result = InvoiceResendResult(
        order_id=o["id"],
        invoice_number=nf["number"],
        protocol=proto,
        channel=channel,
        destination_masked=dest,
    )
    return ok(
        result,
        f"NF-e {nf['number']} do pedido {o['id']} reenviada para {dest}. Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="invoices:write",
    title="Corrigir nota fiscal",
    annotations=WRITE,
    result=InvoiceCorrectionResult,
    description="""
Pede carta de correção (CC-e) de nome, endereço ou inscrição estadual numa nota fiscal já \
emitida, em até 30 dias da emissão. CPF/CNPJ não se corrige por carta.
WHEN TO USE: "meu nome saiu errado na nota", "a NF veio com endereço errado".
DON'T USE FOR: atualizar os dados para as próximas notas (use update_billing_data); mudar \
endereço de entrega (use update_delivery_address); nota não emitida (use get_invoice).
PARAMETERS: field = nome | endereco | inscricao_estadual; correct_value = valor correto dito \
pelo cliente; order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: protocolo e prazo; repasse sem alterar.
""",
    examples=[
        "Meu nome saiu errado na nota fiscal",
        "A NF veio com o endereço antigo, precisa corrigir",
        "A inscrição estadual da empresa está errada na nota",
        "Quero uma carta de correção da nota do pedido",
    ],
    keywords=["corrigir nota", "carta de correcao", "cce", "nota errada", "dados errados na nf"],
)
async def request_invoice_correction(
    field: Annotated[
        Literal["nome", "endereco", "inscricao_estadual"], Field(description="Campo a corrigir")
    ],
    correct_value: Annotated[
        str, Field(description="Valor correto dito pelo cliente", min_length=2, max_length=200)
    ],
    order_id: OrderId = None,
) -> ToolResult:
    o, nf = _invoice(order_id)
    if days_since(nf["issued_at"]) > W["invoice_correction_days_after_issue"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A NF-e {nf['number']} foi emitida há mais de "
            f"{W['invoice_correction_days_after_issue']} dias e não aceita carta de correção.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    if field == "inscricao_estadual" and BILLING[o["customer_id"]]["doc_type"] != "cnpj":
        raise ToolFailure(
            "VALIDATION_ERROR",
            "Inscrição estadual só existe em compras com CNPJ.",
            recoverable=True,
        )
    proto = protocol(
        "NFC",
        "request_invoice_correction",
        {"order_id": o["id"], "field": field, "value": correct_value},
    )
    until = days_from_today(SLA["invoice_correction_business_days"] + 2)
    result = InvoiceCorrectionResult(
        order_id=o["id"],
        invoice_number=nf["number"],
        protocol=proto,
        field=field,
        expected_by=until,
    )
    return ok(
        result,
        f"Carta de correção da NF-e {nf['number']} ({field}) solicitada. Protocolo {proto}; "
        f"emissão até {until}.",
    )


@large_tool(
    skill=SKILL,
    scope="invoices:write",
    title="Emitir nota de devolução",
    annotations=WRITE,
    result=ReturnInvoiceResult,
    description="""
Emite a nota fiscal de devolução exigida quando a compra foi feita com CNPJ (empresa), para \
acompanhar o produto devolvido em até 30 dias da entrega.
WHEN TO USE: "comprei pela empresa e preciso devolver", "pediram nota de devolução".
DON'T USE FOR: devolução de compra com CPF (use create_return_request); etiqueta de postagem \
(use generate_return_label); vendedor parceiro que recusou a devolução (use \
open_seller_mediation).
PARAMETERS: order_id opcional se o cliente tem um só pedido; sku opcional se o pedido tem um \
só item.
CONFIRMATION: não requer.
RESULT: número da nota de devolução e prazo de postagem; repasse sem alterar.
""",
    examples=[
        "Comprei no CNPJ da empresa e preciso devolver, como fica a nota?",
        "A transportadora pediu nota fiscal de devolução",
        "Preciso da NF de devolução para mandar o produto de volta",
        "Somos pessoa jurídica, como emitimos a devolução fiscal?",
    ],
    keywords=["nota de devolucao", "nf de devolucao", "cnpj", "empresa", "devolucao fiscal"],
)
async def issue_return_invoice(
    order_id: OrderId = None,
    sku: Annotated[
        str | None, Field(description="SKU do item. Omita se o pedido tem um só item")
    ] = None,
) -> ToolResult:
    o = resolve_order(order_id)
    if not o["delivered_at"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} ainda não foi entregue (status {o['status']}).",
            recoverable=False,
            suggested_tool="track_shipment" if o["shipment_id"] else "get_order_status",
        )
    if BILLING[o["customer_id"]]["doc_type"] != "cnpj":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} foi comprado com CPF; a devolução não exige nota fiscal.",
            recoverable=False,
            suggested_tool=after_delivery_next_step(o),
        )
    if days_since(o["delivered_at"]) > W["return_invoice_days_after_delivery"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O prazo de {W['return_invoice_days_after_delivery']} dias para devolver o pedido "
            f"{o['id']} terminou.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    item = pick_sku(o, sku)
    nf = INVOICES_BY_ORDER[o["id"]]
    number = str(
        500000 + int(hashlib.sha256(f"{o['id']}|{item['sku']}".encode()).hexdigest(), 16) % 100000
    )
    post_by = days_from_today(W["return_post_by_days"])
    amount = Money(amount=round(item["unit_price"]["amount"] * item["quantity"], 2))
    result = ReturnInvoiceResult(
        order_id=o["id"],
        return_invoice_number=number,
        reference_invoice=nf["number"],
        sku=item["sku"],
        amount=amount,
        post_by=post_by,
    )
    return ok(
        result,
        f"Nota fiscal de devolução {number} emitida para {item['name']} (pedido {o['id']}, "
        f"referência NF-e {nf['number']}), {brl(amount)}. Poste o produto com a nota até "
        f"{post_by}.",
    )


@large_tool(
    skill=SKILL,
    scope="invoices:read",
    title="Comprovante de compra",
    annotations=READ,
    result=PurchaseReceiptResult,
    description="""
Emite o comprovante de compra de um pedido pago: código de autenticação, data e forma de \
pagamento, parcelas e valor.
WHEN TO USE: "preciso de um comprovante da compra", "recibo para reembolso da empresa".
DON'T USE FOR: nota fiscal (use get_invoice); saber se o pagamento foi aprovado (use \
get_payment_status).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: dados do comprovante; repasse o código sem alterar.
""",
    examples=[
        "Preciso de um comprovante da compra para a empresa me reembolsar",
        "Tem como gerar um recibo do pedido?",
        "Quero o comprovante de pagamento da minha compra",
        "Me manda o comprovante com o valor pago",
    ],
    keywords=["comprovante", "recibo", "comprovante de compra", "comprovante de pagamento"],
)
async def get_purchase_receipt(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    p = PAYMENTS[o["payment_id"]]
    if not p["paid_at"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pagamento do pedido {o['id']} ainda não foi confirmado (status {p['status']}).",
            recoverable=False,
            suggested_tool="get_payment_status",
        )
    code = hashlib.sha256(f"receipt|{p['id']}".encode()).hexdigest()[:12].upper()
    result = PurchaseReceiptResult(
        order_id=o["id"],
        receipt_code=code,
        paid_at=p["paid_at"],
        method=p["method"],
        installments=p["installments"],
        amount=Money(**p["amount"]),
        payment_status=p["status"],
    )
    return ok(
        result,
        f"Comprovante {code} do pedido {o['id']}: {brl(p['amount'])} pago em {p['paid_at']} "
        f"via {p['method']} em {p['installments']}x (status {p['status']}).",
    )


@large_tool(
    skill=SKILL,
    scope="customer:write",
    title="Atualizar dados de faturamento",
    annotations=WRITE,
    result=BillingUpdateResult,
    description="""
Atualiza os dados de faturamento do cadastro (nome ou razão social, endereço de cobrança, \
inscrição estadual) usados nas próximas notas fiscais.
WHEN TO USE: "quero que as próximas notas saiam com a razão social nova", "mudei o endereço \
de cobrança".
DON'T USE FOR: corrigir uma nota já emitida (use request_invoice_correction); endereço de \
entrega de um pedido (use update_delivery_address); e-mail ou telefone (use \
update_contact_info).
PARAMETERS: field = nome | endereco_cobranca | inscricao_estadual; new_value = valor novo dito \
pelo cliente. CPF/CNPJ não pode ser trocado.
CONFIRMATION: não requer.
RESULT: protocolo e início da vigência; repasse sem alterar.
""",
    examples=[
        "Quero que as próximas notas saiam com a razão social nova da empresa",
        "Mudei o endereço de cobrança, atualiza no cadastro",
        "Atualiza a inscrição estadual da minha empresa",
        "Meu nome mudou depois do casamento, quero atualizar para as notas",
    ],
    keywords=["dados de faturamento", "razao social", "endereco de cobranca", "cadastro fiscal"],
)
async def update_billing_data(
    field: Annotated[
        Literal["nome", "endereco_cobranca", "inscricao_estadual"],
        Field(description="Campo a atualizar"),
    ],
    new_value: Annotated[
        str, Field(description="Valor novo dito pelo cliente", min_length=2, max_length=200)
    ],
) -> ToolResult:
    c = get_customer()
    if field == "inscricao_estadual" and BILLING[c["id"]]["doc_type"] != "cnpj":
        raise ToolFailure(
            "VALIDATION_ERROR",
            "Inscrição estadual só existe em cadastros com CNPJ.",
            recoverable=True,
        )
    proto = protocol("FAT", "update_billing_data", {"field": field, "value": new_value})
    result = BillingUpdateResult(
        customer_id=c["id"],
        protocol=proto,
        field=field,
        new_value=new_value,
        effective_from=SLA["billing_update_effective"],
    )
    return ok(
        result,
        f'Dados de faturamento ({field}) atualizados para "{new_value}"; valem a partir da '
        f"{SLA['billing_update_effective']}. Protocolo {proto}.",
    )
