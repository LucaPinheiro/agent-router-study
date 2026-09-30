"""Skill trocas_devolucoes: check_return_eligibility, create_return_request, generate_return_label,
create_exchange, open_warranty_claim."""

from datetime import date, timedelta
from typing import Annotated, Any, Literal, get_args

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    ORDERS,
    POLICIES,
    READ,
    REFUNDS_BY_ORDER,
    RETURNS,
    TODAY,
    WRITE,
    ToolFailure,
    after_delivery_next_step,
    brl,
    catalog_tool,
    days_from_today,
    ensure_no_money_back,
    get_customer,
    ok,
    open_return,
    pick_sku,
    protocol,
    resolve_order,
)
from mcp_server.models import (
    EligibilityOption,
    ExchangeResult,
    Money,
    ReturnEligibilityResult,
    ReturnLabelResult,
    ReturnRequestResult,
    WarrantyClaimResult,
)

SKILL = "trocas_devolucoes"
W = POLICIES["windows"]
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]
Sku = Annotated[str | None, Field(description="SKU do item. Omita se o pedido tem um só item")]
ReturnReason = Literal["arrependimento", "defeito", "avariado", "produto_errado", "tamanho_errado"]


def _days_since_delivery(o: dict[str, Any]) -> int:
    if not o["delivered_at"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} ainda não foi entregue (status {o['status']}).",
            recoverable=False,
            suggested_tool="track_shipment" if o["shipment_id"] else "get_order_status",
        )
    return (TODAY - date.fromisoformat(o["delivered_at"])).days


def _plus(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _return_limit(reason: str) -> int:
    return (
        W["arrependimento_days_after_delivery"]
        if reason == "arrependimento"
        else W["return_or_exchange_days_after_delivery"]
    )


def _return_id(order_id: str, reason: str, skus: list[str]) -> str:
    return protocol(
        "DEV", "create_return_request", {"order_id": order_id, "reason": reason, "skus": skus}
    )


def _minted_return(return_id: str, customer: dict[str, Any]) -> dict[str, Any] | None:
    """Return that create_return_request would have minted with this id for this customer.

    Writes don't persist, so a return opened earlier in the conversation is recognised by
    recomputing its deterministic id over every call create_return_request would accept."""
    for oid in customer["order_ids"]:
        o = ORDERS[oid]
        if not o["delivered_at"] or open_return(o) or oid in REFUNDS_BY_ORDER:
            continue
        days = (TODAY - date.fromisoformat(o["delivered_at"])).days
        sku_sets = [[i["sku"] for i in o["items"]]] + [[i["sku"]] for i in o["items"]]
        for reason in get_args(ReturnReason):
            if days > _return_limit(reason):
                continue
            for skus in sku_sets:
                if _return_id(oid, reason, skus) == return_id:
                    return {
                        "id": return_id,
                        "order_id": oid,
                        "post_by": days_from_today(W["return_post_by_days"]),
                    }
    return None


@catalog_tool(
    skill=SKILL,
    scope="returns:read",
    title="Verificar elegibilidade de devolução",
    annotations=READ,
    result=ReturnEligibilityResult,
    description="""
Verifica se um pedido entregue ainda pode ser devolvido, trocado ou coberto pela garantia, com \
o prazo de cada opção.
WHEN TO USE: "ainda dá para devolver?", "posso trocar?", prazo incerto antes de abrir \
devolução, troca ou garantia.
DON'T USE FOR: abrir a devolução (use create_return_request), a troca (use create_exchange) ou \
a garantia (use open_warranty_claim); regra geral sem pedido (use search_help_center).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: opções elegíveis e prazos; repasse sem alterar.
""",
    examples=[
        "Ainda dá tempo de devolver o que comprei?",
        "Posso trocar o produto do pedido O0010?",
        "Recebi há duas semanas, ainda tenho direito à troca?",
        "Meu produto ainda está na garantia?",
    ],
    keywords=["elegivel", "ainda da", "prazo de devolucao", "posso devolver", "posso trocar"],
)
async def check_return_eligibility(order_id: OrderId = None) -> ToolResult:
    o = resolve_order(order_id)
    days = _days_since_delivery(o)
    d0 = o["delivered_at"]
    ret, refund = open_return(o), REFUNDS_BY_ORDER.get(o["id"])
    free = ret is None and refund is None
    options = [
        EligibilityOption(
            type="arrependimento",
            eligible=free and days <= W["arrependimento_days_after_delivery"],
            deadline=_plus(d0, W["arrependimento_days_after_delivery"]),
            tool="create_return_request",
        ),
        EligibilityOption(
            type="devolucao_troca",
            eligible=free and days <= W["return_or_exchange_days_after_delivery"],
            deadline=_plus(d0, W["return_or_exchange_days_after_delivery"]),
            tool="create_return_request | create_exchange",
        ),
        EligibilityOption(
            type="garantia",
            eligible=W["return_or_exchange_days_after_delivery"]
            < days
            <= W["warranty_days_after_delivery"],
            deadline=_plus(d0, W["warranty_days_after_delivery"]),
            tool="open_warranty_claim",
        ),
    ]
    eligible = [opt for opt in options if opt.eligible]
    result = ReturnEligibilityResult(
        order_id=o["id"],
        delivered_at=d0,
        eligible=bool(eligible),
        options=options,
        open_return_id=ret["id"] if ret else None,
        refund_id=refund["id"] if refund else None,
    )
    if eligible:
        text = "; ".join(f"{opt.type} até {opt.deadline}" for opt in eligible)
        text = f"Pedido {o['id']}, entregue em {d0}, é elegível para: {text}."
    elif free:
        text = f"Pedido {o['id']}, entregue em {d0}, está fora de todos os prazos."
    else:
        text = f"Pedido {o['id']}, entregue em {d0}, não admite nova devolução ou troca."
    if ret:
        text += f" Já existe a devolução {ret['id']} aberta (postagem até {ret['post_by']})."
    if refund:
        text += f" Já existe o reembolso {refund['id']} (status {refund['status']})."
    return ok(result, text)


@catalog_tool(
    skill=SKILL,
    scope="returns:write",
    title="Abrir devolução",
    annotations=WRITE,
    result=ReturnRequestResult,
    description="""
Abre a devolução de produto entregue, com reembolso após a loja receber o item.
WHEN TO USE: "quero devolver", arrependimento em até 7 dias; defeito, avaria ou produto errado \
em até 30 dias da entrega.
DON'T USE FOR: pedido não enviado (use cancel_order); trocar tamanho ou cor (use \
create_exchange); defeito após 30 dias (use open_warranty_claim); pedido extraviado (use \
request_refund).
PARAMETERS: reason = arrependimento | defeito | avariado | produto_errado | tamanho_errado; sku \
opcional (omitido = pedido inteiro).
CONFIRMATION: não requer.
RESULT: id da devolução, valor e prazo de postagem; repasse sem alterar.
""",
    examples=[
        "Quero devolver o produto que recebi",
        "Mudei de ideia sobre o produto e vou mandar de volta",
        "O produto chegou quebrado, quero devolver",
        "Veio um item diferente do que eu pedi",
    ],
    keywords=["devolver", "devolucao", "arrependimento", "chegou quebrado", "produto errado"],
)
async def create_return_request(
    reason: Annotated[ReturnReason, Field(description="Motivo da devolução")],
    order_id: OrderId = None,
    sku: Sku = None,
) -> ToolResult:
    o = resolve_order(order_id)
    days = _days_since_delivery(o)
    ensure_no_money_back(o)  # also refuses a second return (suggests generate_return_label)
    limit = _return_limit(reason)
    if days > limit:
        warranty = reason == "defeito" and days <= W["warranty_days_after_delivery"]
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O prazo de {limit} dias para devolução por {reason} do pedido {o['id']} terminou.",
            recoverable=False,
            suggested_tool="open_warranty_claim" if warranty else "escalate_to_human",
        )
    items = [pick_sku(o, sku)] if sku else o["items"]
    amount = Money(amount=round(sum(i["unit_price"]["amount"] * i["quantity"] for i in items), 2))
    skus = [i["sku"] for i in items]
    return_id = _return_id(o["id"], reason, skus)
    post_by = days_from_today(W["return_post_by_days"])
    result = ReturnRequestResult(
        order_id=o["id"],
        return_id=return_id,
        reason=reason,
        skus=skus,
        refund_amount=amount,
        post_by=post_by,
    )
    return ok(
        result,
        f"Devolução {return_id} aberta para o pedido {o['id']} ({', '.join(skus)}), "
        f"motivo {reason}. Poste o produto até {post_by}. Reembolso de "
        f"{brl(amount)} após o recebimento.",
    )


@catalog_tool(
    skill=SKILL,
    scope="returns:write",
    title="Gerar etiqueta de devolução",
    annotations=WRITE,
    result=ReturnLabelResult,
    description="""
Gera a etiqueta de postagem de uma devolução já aberta.
WHEN TO USE: "preciso da etiqueta", "como envio o produto de volta?" depois de abrir a devolução.
DON'T USE FOR: abrir a devolução (use create_return_request); rastrear a entrega de um pedido \
(use track_shipment).
PARAMETERS: return_id informado pelo cliente ou devolvido por create_return_request; senão \
order_id (opcional se há um só pedido).
CONFIRMATION: não requer.
RESULT: código da etiqueta, transportadora e prazo de postagem; repasse sem alterar.
""",
    examples=[
        "Preciso da etiqueta para devolver o produto",
        "Como faço para enviar o produto de volta?",
        "Gera a etiqueta da devolução DEV-1A2B3C4D",
        "Já abri a devolução, cadê o código de postagem?",
    ],
    keywords=["etiqueta", "postagem", "codigo de postagem", "enviar de volta", "logistica reversa"],
)
async def generate_return_label(
    return_id: Annotated[
        str | None, Field(description="Id da devolução (ex.: DEV-1A2B3C4D), se informado")
    ] = None,
    order_id: OrderId = None,
) -> ToolResult:
    customer = get_customer()
    if return_id:
        rid = return_id.strip().upper()
        ret = RETURNS.get(rid)
        if ret is None or ret["order_id"] not in customer["order_ids"]:
            ret = _minted_return(rid, customer)
        if ret is None:
            raise ToolFailure(
                "NOT_FOUND",
                f"Devolução {return_id} não encontrada para este cliente; confira o id ou "
                "informe order_id.",
                recoverable=True,
            )
    else:
        o = resolve_order(order_id)
        _days_since_delivery(o)
        ret = open_return(o)
        if ret is None:
            # D3: never point back to create_return_request: writes don't persist, so a return
            # opened in this conversation is only found by its return_id (else a loop)
            nxt = after_delivery_next_step(o)
            raise ToolFailure(
                "NOT_FOUND",
                f"Não há devolução registrada para o pedido {o['id']}; se ela acabou de ser "
                "aberta, informe o return_id retornado por create_return_request.",
                recoverable=True,
                suggested_tool=None if nxt == "create_return_request" else nxt,
            )
    label = protocol("ETQ", "generate_return_label", {"return_id": ret["id"]})
    o = ORDERS[ret["order_id"]]
    result = ReturnLabelResult(
        order_id=o["id"],
        return_id=ret["id"],
        label_code=label,
        carrier="Correios",
        post_by=ret["post_by"],
    )
    return ok(
        result,
        f"Etiqueta {label} da devolução {ret['id']} (pedido {o['id']}): poste nos "
        f"Correios até {ret['post_by']}.",
    )


@catalog_tool(
    skill=SKILL,
    scope="returns:write",
    title="Abrir troca",
    annotations=WRITE,
    result=ExchangeResult,
    description="""
Abre a troca de um item entregue por outro tamanho, cor ou variação do mesmo produto.
WHEN TO USE: "veio no tamanho errado, quero trocar", "quero outra cor", em até 30 dias da \
entrega.
DON'T USE FOR: dinheiro de volta (use create_return_request); defeito após 30 dias (use \
open_warranty_claim); pedido não entregue (use get_order_status).
PARAMETERS: new_variant = tamanho, cor ou variação dita pelo cliente; sku opcional se o pedido \
tem um só item.
CONFIRMATION: não requer.
RESULT: id da troca e prazo de postagem; repasse sem alterar.
""",
    examples=[
        "O calçado ficou pequeno, troca por um 41",
        "Quero trocar a camiseta por uma G",
        "Dá para trocar a cor da jaqueta?",
        "Ficou apertado, quero um número maior",
    ],
    keywords=["trocar", "troca", "tamanho", "cor", "numero maior", "outra variacao"],
)
async def create_exchange(
    new_variant: Annotated[
        str,
        Field(description="Tamanho, cor ou variação desejada (ex.: 41, G, azul)", max_length=60),
    ],
    order_id: OrderId = None,
    sku: Sku = None,
) -> ToolResult:
    o = resolve_order(order_id)
    days = _days_since_delivery(o)
    if days > W["return_or_exchange_days_after_delivery"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O prazo de {W['return_or_exchange_days_after_delivery']} dias para troca do pedido "
            f"{o['id']} terminou.",
            recoverable=False,
            suggested_tool="open_warranty_claim"
            if days <= W["warranty_days_after_delivery"]
            else "escalate_to_human",
        )
    ensure_no_money_back(o)
    item = pick_sku(o, sku)
    exchange_id = protocol(
        "TRC",
        "create_exchange",
        {"order_id": o["id"], "sku": item["sku"], "new_variant": new_variant},
    )
    post_by = days_from_today(W["return_post_by_days"])
    result = ExchangeResult(
        order_id=o["id"],
        exchange_id=exchange_id,
        sku=item["sku"],
        new_variant=new_variant,
        post_by=post_by,
    )
    return ok(
        result,
        f"Troca {exchange_id} aberta: {item['name']} ({item['sku']}) do pedido "
        f"{o['id']} por {new_variant}. Poste o item até {post_by}.",
    )


@catalog_tool(
    skill=SKILL,
    scope="returns:write",
    title="Acionar garantia",
    annotations=WRITE,
    result=WarrantyClaimResult,
    description="""
Aciona a garantia de um produto com defeito que apareceu após 30 dias e em até 12 meses da \
entrega.
WHEN TO USE: "parou de funcionar", "deu defeito depois de alguns meses".
DON'T USE FOR: defeito em até 30 dias da entrega ou produto que chegou quebrado (use \
create_return_request ou create_exchange); pedido não entregue (use track_shipment).
PARAMETERS: defect_description = defeito nas palavras do cliente; sku opcional se o pedido tem \
um só item.
CONFIRMATION: não requer.
RESULT: id do chamado de garantia e prazo de resposta; repasse sem alterar.
""",
    examples=[
        "Meu fone parou de funcionar depois de 3 meses",
        "A cafeteira deu defeito, quero acionar a garantia",
        "O relógio comprado há meio ano não liga mais",
        "Produto com defeito de fábrica depois de alguns meses de uso",
    ],
    keywords=["garantia", "parou de funcionar", "defeito", "nao liga", "conserto", "assistencia"],
)
async def open_warranty_claim(
    defect_description: Annotated[
        str, Field(description="Defeito nas palavras do cliente", max_length=500)
    ],
    order_id: OrderId = None,
    sku: Sku = None,
) -> ToolResult:
    o = resolve_order(order_id)
    days = _days_since_delivery(o)
    if days <= W["return_or_exchange_days_after_delivery"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} foi entregue há {days} dias; defeitos em até "
            f"{W['return_or_exchange_days_after_delivery']} dias são tratados por devolução ou "
            "troca.",
            recoverable=False,
            suggested_tool=after_delivery_next_step(o),
        )
    if days > W["warranty_days_after_delivery"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A garantia do pedido {o['id']} terminou em "
            f"{_plus(o['delivered_at'], W['warranty_days_after_delivery'])}.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    item = pick_sku(o, sku)
    claim_id = protocol(
        "GAR",
        "open_warranty_claim",
        {"order_id": o["id"], "sku": item["sku"], "defect": defect_description},
    )
    until = _plus(o["delivered_at"], W["warranty_days_after_delivery"])
    response_by = days_from_today(21)
    result = WarrantyClaimResult(
        order_id=o["id"],
        claim_id=claim_id,
        sku=item["sku"],
        warranty_until=until,
        expected_response_by=response_by,
    )
    return ok(
        result,
        f"Garantia {claim_id} aberta para {item['name']} ({item['sku']}) do pedido "
        f"{o['id']}. Garantia válida até {until}; resposta até {response_by}.",
    )
