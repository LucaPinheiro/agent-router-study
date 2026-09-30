"""Global tools (always exposed): get_customer_profile, search_help_center, escalate_to_human."""

import re
import unicodedata
from typing import Annotated

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import (
    ORDERS,
    POLICIES,
    READ,
    WRITE,
    ToolFailure,
    catalog_tool,
    get_customer,
    ok,
    order_ref,
    protocol,
    resolve_order,
)
from mcp_server.models import (
    Address,
    Article,
    CustomerProfileResult,
    EscalationResult,
    HelpCenterResult,
)

SKILL = "global"


def _mask_email(email: str) -> str:
    user, domain = email.split("@", 1)
    return f"{user[0]}***@{domain}"


@catalog_tool(
    skill=SKILL,
    scope="customer:read",
    title="Perfil do cliente",
    annotations=READ,
    result=CustomerProfileResult,
    description="""
Retorna o perfil do cliente autenticado: nome, e-mail mascarado, endereço padrão e a lista \
resumida dos pedidos (id, status, data, total).
WHEN TO USE: o cliente pergunta pelos próprios dados ou pedidos, ou é preciso descobrir qual \
pedido ele quer quando não informou o número.
DON'T USE FOR: detalhes de um pedido (use get_order_status); rastreio (use track_shipment); \
pagamento (use get_payment_status).
PARAMETERS: nenhum; o cliente vem da requisição autenticada.
CONFIRMATION: não requer.
RESULT: dados do perfil; repasse IDs, datas e valores sem alterar.
""",
    examples=[
        "Quais pedidos eu tenho com vocês?",
        "Qual endereço está no meu cadastro?",
        "Não lembro o número do meu pedido",
        "Me mostra meus dados de cliente",
    ],
    keywords=["perfil", "cadastro", "meus pedidos", "meus dados", "numero do pedido"],
)
async def get_customer_profile() -> ToolResult:
    c = get_customer()
    orders = [order_ref(ORDERS[oid]) for oid in c["order_ids"]]
    result = CustomerProfileResult(
        customer_id=c["id"],
        name=c["name"],
        email_masked=_mask_email(c["email"]),
        tier=c["tier"],
        member_since=c["member_since"],
        default_address=Address(**c["default_address"]),
        orders=orders,
    )
    lines = "; ".join(f"{o.order_id} ({o.status}, {o.created_at})" for o in orders)
    return ok(result, f"Cliente {c['id']} ({c['name']}) tem {len(orders)} pedido(s): {lines}.")


def _norm(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return {w for w in re.findall(r"[a-z0-9]+", text) if len(w) > 2}


@catalog_tool(
    skill=SKILL,
    scope="public:read",
    title="Buscar na central de ajuda",
    annotations=READ,
    result=HelpCenterResult,
    description="""
Busca artigos da central de ajuda com as políticas da loja: prazos de troca, devolução, \
reembolso, entrega, garantia e formas de pagamento.
WHEN TO USE: dúvida genérica sobre regra ou prazo, sem ação sobre um pedido concreto \
("qual o prazo para devolver?").
DON'T USE FOR: situação de um pedido, pagamento, entrega ou reembolso concreto (use \
get_order_status, get_payment_status, track_shipment ou get_refund_status); executar uma ação.
PARAMETERS: query = a dúvida em poucas palavras.
CONFIRMATION: não requer.
RESULT: até 3 artigos com título e resumo; cite prazos sem alterar.
""",
    examples=[
        "Qual o prazo para devolver um produto?",
        "Vocês parcelam no cartão?",
        "Quanto tempo demora o estorno no Pix?",
        "Como funciona a garantia?",
    ],
    keywords=["politica", "prazo", "regra", "como funciona", "duvida", "central de ajuda"],
)
async def search_help_center(
    query: Annotated[
        str, Field(description="Dúvida do cliente em poucas palavras", max_length=300)
    ],
) -> ToolResult:
    terms = _norm(query)
    if not terms:
        raise ToolFailure(
            "VALIDATION_ERROR",
            "A busca precisa de ao menos uma palavra com 3 letras ou mais.",
            recoverable=True,
        )
    scored = []
    for art in POLICIES["articles"]:
        vocab = _norm(" ".join([art["title"], art["summary"], *art["keywords"]]))
        score = len(terms & vocab)
        if score:
            scored.append((-score, art["id"], art))
    if not scored:
        raise ToolFailure(
            "NOT_FOUND",
            "Nenhum artigo da central de ajuda corresponde à busca.",
            recoverable=False,
            suggested_tool="escalate_to_human",
        )
    top = [a for _, _, a in sorted(scored)[:3]]
    result = HelpCenterResult(
        query=query,
        articles=[Article(id=a["id"], title=a["title"], summary=a["summary"]) for a in top],
    )
    text = " ".join(f"[{a['id']}] {a['title']}: {a['summary']}" for a in top)
    return ok(result, text)


@catalog_tool(
    skill=SKILL,
    scope="support:write",
    title="Escalar para atendente humano",
    annotations=WRITE,
    result=EscalationResult,
    description="""
Abre um chamado para atendimento humano e retorna o protocolo e o prazo de retorno.
WHEN TO USE: o cliente pede um atendente; o assunto está fora do escopo das outras tools \
(vagas, produtos novos, preços, nota fiscal); uma tool retornou erro não recuperável.
DON'T USE FOR: pedidos que uma tool resolve (cancelar, reembolsar, trocar, rastrear); \
dúvida de política (use search_help_center).
PARAMETERS: reason = resumo curto do pedido do cliente; order_id só se o cliente citou um pedido.
CONFIRMATION: não requer.
RESULT: protocolo e prazo de retorno; repasse sem alterar.
""",
    examples=[
        "Quero falar com um atendente",
        "Me passa para uma pessoa de verdade",
        "Vocês têm vaga de emprego?",
        "Preciso corrigir a nota fiscal da minha compra",
    ],
    keywords=["atendente", "humano", "pessoa", "reclamacao", "falar com alguem"],
)
async def escalate_to_human(
    reason: Annotated[
        str,
        Field(description="Resumo curto do que o cliente precisa", min_length=3, max_length=500),
    ],
    order_id: Annotated[
        str | None, Field(description="Pedido citado pelo cliente (ex.: O0001), se houver")
    ] = None,
) -> ToolResult:
    get_customer()
    oid = resolve_order(order_id)["id"] if order_id else None
    hours = POLICIES["sla"]["human_support_hours"]
    ticket = protocol("ATD", "escalate_to_human", {"reason": reason, "order_id": oid})
    result = EscalationResult(
        ticket_id=ticket, order_id=oid, queue="atendimento_geral", response_within_hours=hours
    )
    ref = f" sobre o pedido {oid}" if oid else ""
    return ok(result, f"Chamado {ticket} aberto{ref}. Um atendente responde em até {hours} horas.")
