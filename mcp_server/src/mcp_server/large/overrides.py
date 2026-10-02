"""Large-profile overlay of the 18 original tools (plan §1, "Original tools").

The originals keep their code and their small-profile definitions byte for byte. In the large
profile only, each one is served as a COPY whose description gains DON'T USE FOR pointers to its
new confusable siblings: the 44 new tools point at the originals, so without this overlay the
catalog would be one-sided (old -> new pointers missing).

Besides the pointers, `REPLACE` fixes the two statements that the large catalog makes false
(escalate_to_human listed prices and invoices as out of scope and had an invoice example), and
search_help_center is rebound to the large policy articles (same algorithm, same schema).
"""

from __future__ import annotations

from typing import Any

from fastmcp.tools.base import ToolResult

from mcp_server.core import RDNS, REGISTRY, CatalogTool, ToolFailure, fail, ok
from mcp_server.large.data import POLICIES_L
from mcp_server.models import Article, HelpCenterResult
from mcp_server.tools.globals import _norm

AVOID = "DON'T USE FOR:"

# tool -> clauses appended to its DON'T USE FOR line (same "(use tool)" convention)
POINTERS: dict[str, str] = {
    "get_order_status": "ordem de serviço de instalação ou visita (use get_service_order_status); "
    "próxima entrega da assinatura (use get_subscription)",
    "track_shipment": "pedido enviado por vendedor parceiro (use track_seller_shipment)",
    "update_delivery_address": "dados da nota fiscal (use update_billing_data); e-mail ou "
    "celular (use update_contact_info)",
    "reschedule_delivery": "próxima entrega da assinatura (use change_subscription_date); dia "
    "do técnico (use reschedule_technical_visit)",
    "cancel_order": "assinatura recorrente (use cancel_subscription); instalação ou visita "
    "técnica (use cancel_service_order)",
    "get_payment_status": "comprovante (use get_purchase_receipt) ou nota fiscal (use "
    "get_invoice); fatura do cartão da loja (use get_card_bill)",
    "generate_boleto_second_copy": "fatura do cartão da loja (use generate_card_bill_copy)",
    "request_refund": "preço que baixou após a compra (use request_price_protection); cupom não "
    "descontado (use report_coupon_not_applied)",
    "get_refund_status": "cashback (use get_cashback_status); pontos que não caíram (use "
    "claim_missing_points)",
    "dispute_charge": "cartão da loja (use contest_card_transaction); compra de vendedor "
    "parceiro (use open_seller_mediation)",
    "check_return_eligibility": "garantia estendida (use check_extended_warranty)",
    "create_return_request": "compra com CNPJ, que exige nota de devolução (use "
    "issue_return_invoice); devolução recusada por vendedor parceiro (use open_seller_mediation)",
    "generate_return_label": "nota fiscal de devolução (use issue_return_invoice)",
    "open_warranty_claim": "técnico em casa para eletrodoméstico (use request_technical_visit); "
    "só consultar a cobertura (use check_extended_warranty)",
    "get_customer_profile": "trocar e-mail ou celular (use update_contact_info); nível no "
    "programa de pontos (use get_loyalty_tier)",
    "search_help_center": "regulamento de uma campanha (use get_promotion_terms); andamento de "
    "um protocolo (use check_protocol_status)",
    "escalate_to_human": "dúvida ou ação de nota fiscal, cupom, cadastro, assinatura, pontos ou "
    "cartão da loja (use a tool do assunto)",
}
# tool -> [(old, new)] exact replacements in the description
REPLACE: dict[str, list[tuple[str, str]]] = {
    "escalate_to_human": [
        ("(vagas, produtos novos, preços, nota fiscal)", "(vagas, produtos novos, senha, atacado)"),
    ],
}
# tool -> replacement `_meta` examples (only where an original example became a new tool's case)
EXAMPLES: dict[str, list[str]] = {
    "escalate_to_human": [
        "Tem como eu ser atendido por alguém da equipe?",
        "Me passa para uma pessoa de verdade",
        "Estão contratando? Queria mandar meu currículo",
        "Esqueci a senha e não consigo entrar na conta",
    ],
}


def overlay_description(name: str, description: str) -> str:
    for old, new in REPLACE.get(name, []):
        assert old in description, f"{name}: overlay target {old!r} missing"
        description = description.replace(old, new)
    extra = POINTERS.get(name)
    if not extra:
        return description
    lines = description.split("\n")
    idx = next(i for i, ln in enumerate(lines) if ln.startswith(AVOID))
    end = idx
    while not lines[end].rstrip().endswith("."):  # the section may wrap over several lines
        end += 1
    lines[end] = f"{lines[end].rstrip()[:-1]}; {extra}."
    return "\n".join(lines)


async def _search_help_center_large(query: str) -> ToolResult:
    """search_help_center over the large policy articles (same scoring as the original)."""
    try:
        terms = _norm(query)
        if not terms:
            raise ToolFailure(
                "VALIDATION_ERROR",
                "A busca precisa de ao menos uma palavra com 3 letras ou mais.",
                recoverable=True,
            )
        scored = []
        for art in POLICIES_L["articles"]:
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
        return ok(result, " ".join(f"[{a['id']}] {a['title']}: {a['summary']}" for a in top))
    except ToolFailure as exc:
        return fail(exc.error)


def overlaid_originals() -> list[CatalogTool]:
    """Copies of the 18 original tools for the large profile (REGISTRY itself is untouched)."""
    out: list[CatalogTool] = []
    for tool in REGISTRY:
        update: dict[str, Any] = {
            "description": overlay_description(tool.name, tool.description or ""),
        }
        if tool.name in EXAMPLES:
            update["meta"] = {**(tool.meta or {}), f"{RDNS}/examples": EXAMPLES[tool.name]}
        if tool.name == "search_help_center":
            update["fn"] = _search_help_center_large
        out.append(tool.model_copy(update=update))
    return out
