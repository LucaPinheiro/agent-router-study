"""Skill cartao_loja_crediario (adjacent domain): get_card_bill, generate_card_bill_copy,
contest_card_transaction, request_limit_increase, block_store_card, renegotiate_debt."""

import hashlib
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    DESTRUCTIVE,
    READ,
    TODAY,
    WRITE,
    ToolFailure,
    brl,
    days_from_today,
    ok,
    protocol,
)
from mcp_server.large.data import SLA, W, days_since, large_tool, store_card
from mcp_server.large.models import (
    CardBillCopyResult,
    CardBillResult,
    CardBlockResult,
    CardContestResult,
    CardTransaction,
    DebtRenegotiationResult,
    LimitIncreaseResult,
)
from mcp_server.models import Money

SKILL = "cartao_loja_crediario"


def _active_card() -> dict:
    card = store_card()
    if card["status"] != "active":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O cartão da loja final {card['last4']} está bloqueado ({card['blocked_reason']}).",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    return card


@large_tool(
    skill=SKILL,
    scope="storecard:read",
    title="Fatura do cartão da loja",
    annotations=READ,
    result=CardBillResult,
    description="""
Mostra a fatura atual do cartão da loja (crediário): status, vencimento, valor, mínimo, \
limite disponível e lançamentos.
WHEN TO USE: "quanto veio a fatura do cartão da loja?", "qual o vencimento?", "quero ver os \
lançamentos".
DON'T USE FOR: pagamento de um pedido com cartão de banco (use get_payment_status); emitir \
boleto da fatura (use generate_card_bill_copy).
PARAMETERS: nenhum; o cartão vem do cliente autenticado.
CONFIRMATION: não requer.
RESULT: dados da fatura; repasse valores, datas e IDs sem alterar.
""",
    examples=[
        "Quanto veio a fatura do cartão da loja este mês?",
        "Qual o vencimento do meu crediário?",
        "Quero ver os lançamentos do cartão da loja",
        "Quanto tenho de limite disponível no cartão da loja?",
    ],
    keywords=["fatura do cartao da loja", "crediario", "vencimento", "lancamentos", "limite"],
)
async def get_card_bill() -> ToolResult:
    card = store_card()
    bill = card["bill"]
    result = CardBillResult(
        card_last4=card["last4"],
        card_status=card["status"],
        bill_status=bill["status"],
        due_date=bill["due_date"],
        amount=Money(**bill["amount"]),
        minimum_payment=Money(**bill["minimum_payment"]),
        amount_due=Money(**bill["amount_due"]),
        limit=Money(**card["limit"]),
        available=Money(**card["available"]),
        transactions=[
            CardTransaction(
                **{k: t[k] for k in ("id", "date", "description", "amount", "contested")}
            )
            for t in bill["transactions"]
        ],
    )
    return ok(
        result,
        f"Fatura do cartão da loja final {card['last4']}: {bill['status']}, vencimento "
        f"{bill['due_date']}, total {brl(bill['amount'])}, a pagar {brl(bill['amount_due'])}, "
        f"mínimo {brl(bill['minimum_payment'])}. Limite disponível {brl(card['available'])}.",
    )


@large_tool(
    skill=SKILL,
    scope="storecard:write",
    title="2ª via da fatura do cartão da loja",
    annotations=WRITE,
    result=CardBillCopyResult,
    description="""
Emite a 2ª via (boleto) da fatura do cartão da loja com novo vencimento em 3 dias; atraso \
acima de 30 dias só por renegociação.
WHEN TO USE: "preciso do boleto da fatura do cartão da loja", "perdi a fatura do crediário".
DON'T USE FOR: boleto de um pedido (use generate_boleto_second_copy); ver lançamentos (use \
get_card_bill); fatura em atraso grave (use renegotiate_debt).
PARAMETERS: nenhum; o cartão vem do cliente autenticado.
CONFIRMATION: não requer.
RESULT: linha digitável, valor e vencimento; repasse sem alterar nenhum dígito.
""",
    examples=[
        "Preciso do boleto da fatura do cartão da loja",
        "Perdi a fatura do crediário, gera outra",
        "Manda a segunda via da fatura do cartão da loja",
        "Quero pagar a fatura do cartão da loja, cadê o código de barras?",
    ],
    keywords=["segunda via fatura", "boleto da fatura", "crediario", "cartao da loja"],
)
async def generate_card_bill_copy() -> ToolResult:
    card = store_card()
    bill = card["bill"]
    if bill["status"] == "paid":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A fatura do cartão da loja final {card['last4']} já está paga.",
            recoverable=False,
            suggested_tool="get_card_bill",
        )
    if (card["overdue_days"] or 0) > W["store_card_max_overdue_days_for_copy"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"A fatura está {card['overdue_days']} dias em atraso; o pagamento é feito por "
            "acordo de renegociação.",
            recoverable=False,
            suggested_tool="renegotiate_debt",
        )
    due = days_from_today(W["store_card_bill_copy_due_days"])
    amount = card["overdue_amount"] if card["overdue_days"] else bill["amount_due"]
    barcode = str(int(hashlib.sha256(f"{card['id']}|{due}".encode()).hexdigest(), 16))[:47]
    result = CardBillCopyResult(
        card_last4=card["last4"], barcode=barcode, amount=Money(**amount), due_date=due
    )
    return ok(
        result,
        f"2ª via da fatura do cartão da loja final {card['last4']}: {brl(amount)}, vencimento "
        f"{due}. Linha digitável: {barcode}.",
    )


@large_tool(
    skill=SKILL,
    scope="storecard:write",
    title="Contestar lançamento do cartão da loja",
    annotations=WRITE,
    result=CardContestResult,
    description="""
Contesta um lançamento da fatura do cartão da loja (não reconhecido, duplicado, valor errado \
ou produto não recebido); o valor fica suspenso durante a análise.
WHEN TO USE: "não reconheço essa compra no cartão da loja", "cobraram duas vezes no \
crediário".
DON'T USE FOR: cobrança em cartão de banco (use dispute_charge); problema com vendedor \
parceiro (use open_seller_mediation); perda ou roubo do cartão (use block_store_card).
PARAMETERS: transaction_id = id do lançamento (TX-...), visto em get_card_bill; reason = \
nao_reconhecida | duplicada | valor_divergente | produto_nao_recebido.
CONFIRMATION: não requer.
RESULT: id da contestação e prazo; repasse sem alterar.
""",
    examples=[
        "Não reconheço uma compra na fatura do cartão da loja",
        "Cobraram duas vezes o seguro no meu crediário",
        "Quero contestar um lançamento do cartão da loja",
        "Tem uma compra na fatura do cartão da loja que eu não fiz",
    ],
    keywords=["contestar lancamento", "nao reconheco", "cartao da loja", "crediario", "cobranca"],
)
async def contest_card_transaction(
    transaction_id: Annotated[str, Field(description="Id do lançamento (ex.: TX-1A2B3C4D)")],
    reason: Annotated[
        Literal["nao_reconhecida", "duplicada", "valor_divergente", "produto_nao_recebido"],
        Field(description="Motivo da contestação"),
    ],
) -> ToolResult:
    card = store_card()
    txs = {t["id"]: t for t in card["bill"]["transactions"]}
    tx = txs.get(transaction_id.strip().upper())
    if tx is None:
        raise ToolFailure(
            "NOT_FOUND",
            f"Lançamento {transaction_id.strip()} não encontrado na fatura do cartão da loja.",
            recoverable=True,
            details={"options": list(txs)},
        )
    if tx["contested"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O lançamento {tx['id']} já está contestado (protocolo {tx['contest_protocol']}).",
            recoverable=False,
            suggested_tool="check_protocol_status",
            details={"protocol": tx["contest_protocol"]},
        )
    if days_since(tx["date"]) > W["card_contest_max_days_after_transaction"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O lançamento {tx['id']} tem mais de "
            f"{W['card_contest_max_days_after_transaction']} dias.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    contest_id = protocol("CCL", "contest_card_transaction", {"tx": tx["id"], "reason": reason})
    until = days_from_today(SLA["store_card_contest_days"])
    result = CardContestResult(
        transaction_id=tx["id"],
        contest_id=contest_id,
        amount=Money(**tx["amount"]),
        reason=reason,
        expected_resolution_by=until,
    )
    return ok(
        result,
        f"Contestação {contest_id} aberta para o lançamento {tx['id']} ({tx['description']}, "
        f"{brl(tx['amount'])}), motivo {reason}. Resposta até {until}.",
    )


@large_tool(
    skill=SKILL,
    scope="storecard:write",
    title="Aumentar limite do cartão da loja",
    annotations=WRITE,
    result=LimitIncreaseResult,
    description="""
Pede aumento do limite do cartão da loja; sem atraso, aprova até 1,5 vez o limite atual na \
hora.
WHEN TO USE: "quero mais limite no cartão da loja", "o limite do crediário não dá para a \
compra".
DON'T USE FOR: limite disponível hoje (use get_card_bill); parcelar dívida em atraso (use \
renegotiate_debt).
PARAMETERS: desired_limit = limite total desejado em reais, dito pelo cliente.
CONFIRMATION: não requer.
RESULT: limite anterior, aprovado e pedido; repasse sem alterar.
""",
    examples=[
        "Quero aumentar o limite do cartão da loja",
        "O limite do crediário não dá para a compra que quero fazer",
        "Dá para subir meu limite para 3 mil?",
        "Como consigo mais limite no cartão da loja?",
    ],
    keywords=["aumentar limite", "mais limite", "limite do cartao", "crediario"],
)
async def request_limit_increase(
    desired_limit: Annotated[float, Field(description="Limite total desejado (R$)", gt=0)],
) -> ToolResult:
    card = _active_card()
    if card["overdue_days"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Há fatura em atraso há {card['overdue_days']} dias; o aumento de limite exige as "
            "faturas em dia.",
            recoverable=False,
            suggested_tool="get_card_bill",
        )
    current = card["limit"]["amount"]
    if desired_limit <= current:
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"O limite atual já é {brl(card['limit'])}; informe um valor maior.",
            recoverable=True,
        )
    approved = min(desired_limit, current * W["store_card_limit_increase_max_factor"])
    approved = float(int(approved // 100) * 100)
    proto = protocol("LIM", "request_limit_increase", {"desired": desired_limit})
    result = LimitIncreaseResult(
        card_last4=card["last4"],
        protocol=proto,
        previous_limit=Money(**card["limit"]),
        approved_limit=Money(amount=approved),
        requested_limit=Money(amount=desired_limit),
    )
    return ok(
        result,
        f"Limite do cartão da loja final {card['last4']} aumentado de {brl(card['limit'])} para "
        f"{brl(Money(amount=approved))} (pedido {brl(Money(amount=desired_limit))}). "
        f"Protocolo {proto}.",
    )


@large_tool(
    skill=SKILL,
    scope="storecard:block",
    title="Bloquear cartão da loja",
    annotations=DESTRUCTIVE,
    result=CardBlockResult,
    description="""
Bloqueia definitivamente o cartão da loja por perda, roubo ou suspeita de fraude e pede um \
novo. Irreversível.
WHEN TO USE: "perdi o cartão da loja", "roubaram meu cartão do crediário", "acho que \
clonaram".
DON'T USE FOR: contestar um lançamento (use contest_card_transaction); cartão de banco usado \
num pedido (use dispute_charge).
PARAMETERS: reason = perda | roubo | suspeita_fraude.
CONFIRMATION: o servidor não pede confirmação; a ação é irreversível.
RESULT: protocolo e prazo do novo cartão; repasse sem alterar.
""",
    examples=[
        "Perdi meu cartão da loja, quero bloquear",
        "Roubaram minha bolsa com o cartão do crediário",
        "Acho que clonaram o cartão da loja, bloqueia agora",
        "Preciso bloquear o cartão da loja e pedir outro",
    ],
    keywords=["bloquear cartao", "perdi o cartao", "roubo", "clonado", "cartao da loja"],
)
async def block_store_card(
    reason: Annotated[
        Literal["perda", "roubo", "suspeita_fraude"], Field(description="Motivo do bloqueio")
    ],
) -> ToolResult:
    card = _active_card()
    proto = protocol("BLQ", "block_store_card", {"card": card["id"], "reason": reason})
    by = days_from_today(SLA["store_card_replacement_business_days"] + 2)
    result = CardBlockResult(
        card_last4=card["last4"],
        protocol=proto,
        reason=reason,
        blocked_at=TODAY.isoformat(),
        replacement_by=by,
    )
    return ok(
        result,
        f"Cartão da loja final {card['last4']} bloqueado ({reason}). Protocolo {proto}; o novo "
        f"cartão chega até {by}.",
    )


@large_tool(
    skill=SKILL,
    scope="storecard:write",
    title="Renegociar dívida do cartão da loja",
    annotations=WRITE,
    result=DebtRenegotiationResult,
    description="""
Fecha acordo para parcelar a fatura em atraso do cartão da loja em 2 a 12 parcelas.
WHEN TO USE: "estou com a fatura atrasada e quero parcelar", "quero negociar minha dívida do \
crediário".
DON'T USE FOR: fatura em dia (use generate_card_bill_copy); mais limite (use \
request_limit_increase).
PARAMETERS: installments = número de parcelas (2 a 12).
CONFIRMATION: não requer.
RESULT: id do acordo, valor das parcelas e 1º vencimento; repasse sem alterar.
""",
    examples=[
        "Estou com a fatura do cartão da loja atrasada, quero parcelar",
        "Quero negociar minha dívida do crediário",
        "Dá para dividir o que devo no cartão da loja em 6 vezes?",
        "Tenho parcelas atrasadas, como faço um acordo?",
    ],
    keywords=["renegociar", "acordo", "divida", "atrasada", "parcelar fatura", "crediario"],
)
async def renegotiate_debt(
    installments: Annotated[int, Field(description="Número de parcelas (2 a 12)", ge=2, le=12)],
) -> ToolResult:
    card = store_card()
    if not card["overdue_days"]:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O cartão da loja final {card['last4']} não tem fatura em atraso.",
            recoverable=False,
            suggested_tool="get_card_bill",
        )
    debt = card["overdue_amount"]["amount"]
    each = round(debt / installments, 2)
    agreement = protocol(
        "ACD", "renegotiate_debt", {"card": card["id"], "installments": installments}
    )
    first = days_from_today(7)
    result = DebtRenegotiationResult(
        agreement_id=agreement,
        debt_amount=Money(amount=debt),
        installments=installments,
        installment_amount=Money(amount=each),
        first_due_date=first,
    )
    return ok(
        result,
        f"Acordo {agreement}: dívida de {brl(Money(amount=debt))} em {installments}x de "
        f"{brl(Money(amount=each))}, 1º vencimento em {first}.",
    )
