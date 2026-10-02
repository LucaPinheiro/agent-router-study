"""New global tools of the large profile: update_contact_info, check_protocol_status."""

import re
from typing import Annotated

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import READ, WRITE, ToolFailure, days_from_today, get_customer, ok
from mcp_server.core import protocol as mint
from mcp_server.large.data import PROTOCOLS, large_tool, mask_email
from mcp_server.large.models import ContactUpdateResult, ProtocolStatusResult

SKILL = "global"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PROTOCOL_RE = re.compile(r"^([A-Z]{2,4})-[0-9A-F]{8}$")
# minted by the tools of this server -> (kind, business days to answer)
KINDS = {
    "ATD": ("atendimento", 1),
    "END": ("alteracao_endereco", 1),
    "AGD": ("reagendamento_entrega", 1),
    "CAN": ("cancelamento_pedido", 2),
    "CTS": ("contestacao_cartao_credito", 60),
    "MED": ("mediacao_vendedor", 10),
    "MSG": ("mensagem_vendedor", 3),
    "DEN": ("denuncia_vendedor", 7),
    "NFC": ("correcao_nota_fiscal", 5),
    "AJC": ("ajuste_cupom", 5),
    "PTF": ("pontos_nao_creditados", 10),
    "CCL": ("contestacao_cartao_loja", 30),
    "FAT": ("dados_faturamento", 1),
    "CTT": ("dados_contato", 1),
    "DEV": ("devolucao", 10),
    "TRC": ("troca", 10),
    "GAR": ("acionamento_garantia", 15),
    "AGT": ("reagendamento_visita_tecnica", 1),
    "CNS": ("cancelamento_ordem_servico", 1),
    "PAU": ("pausa_assinatura", 1),
    "CAS": ("cancelamento_assinatura", 1),
    "DTA": ("data_assinatura", 1),
    "ITS": ("itens_assinatura", 1),
    "PGA": ("pagamento_assinatura", 1),
    "ENF": ("reenvio_nota_fiscal", 1),
    "AVL": ("avaliacao_vendedor", 1),
    "LIM": ("aumento_limite", 1),
    "BLQ": ("bloqueio_cartao_loja", 7),
    "ACD": ("acordo_renegociacao", 1),
    "RVP": ("resgate_vale_presente", 1),
}
# protocols that have their own lookup tool (richer answer: amount, deadline, technician)
DEDICATED = {
    "REF": "get_refund_status",
    "OS": "get_service_order_status",
}


@large_tool(
    skill=SKILL,
    scope="customer:write",
    title="Atualizar contato",
    annotations=WRITE,
    result=ContactUpdateResult,
    description="""
Atualiza o e-mail e/ou o celular de contato do cadastro do cliente.
WHEN TO USE: "troquei de e-mail", "meu celular mudou, atualiza no cadastro".
DON'T USE FOR: endereço de entrega de um pedido (use update_delivery_address); dados da nota \
fiscal (use update_billing_data); senha ou login (use escalate_to_human).
PARAMETERS: email e/ou phone ditos pelo cliente (celular com DDD, só dígitos); informe ao \
menos um.
CONFIRMATION: não requer.
RESULT: protocolo e contatos mascarados; repasse sem alterar.
""",
    examples=[
        "Troquei de e-mail, quero atualizar no cadastro",
        "Meu celular mudou, o novo é 11 98888-7766",
        "Atualiza meu telefone de contato",
        "Quero receber os avisos em outro e-mail",
    ],
    keywords=["email", "telefone", "celular", "contato", "atualizar cadastro"],
)
async def update_contact_info(
    email: Annotated[str | None, Field(description="Novo e-mail", max_length=120)] = None,
    phone: Annotated[
        str | None, Field(description="Novo celular com DDD (ex.: 11988887766)", max_length=20)
    ] = None,
) -> ToolResult:
    c = get_customer()
    if not email and not phone:
        raise ToolFailure(
            "VALIDATION_ERROR", "Informe o novo e-mail ou o novo celular.", recoverable=True
        )
    digits = re.sub(r"\D", "", phone or "")
    if email and not EMAIL_RE.match(email.strip()):
        raise ToolFailure("VALIDATION_ERROR", "E-mail inválido.", recoverable=True)
    if phone and len(digits) not in (10, 11):
        raise ToolFailure(
            "VALIDATION_ERROR", "Celular deve ter DDD + 8 ou 9 dígitos.", recoverable=True
        )
    proto = mint("CTT", "update_contact_info", {"email": email, "phone": digits or None})
    result = ContactUpdateResult(
        customer_id=c["id"],
        protocol=proto,
        email_masked=mask_email(email.strip()) if email else None,
        phone_masked=f"({digits[:2]}) *****-{digits[-4:]}" if digits else None,
    )
    changed = ", ".join(
        x
        for x in (
            f"e-mail {result.email_masked}" if email else "",
            f"celular {result.phone_masked}" if digits else "",
        )
        if x
    )
    return ok(result, f"Contato atualizado: {changed}. Protocolo {proto}.")


@large_tool(
    skill=SKILL,
    scope="support:read",
    title="Consultar protocolo",
    annotations=READ,
    result=ProtocolStatusResult,
    description="""
Consulta o andamento de um protocolo de atendimento já aberto (chamado, mediação, correção de \
nota, ajuste de cupom, contestação, alteração de cadastro).
WHEN TO USE: "tenho o protocolo ATD-..., como está?", "e o chamado que abri?".
DON'T USE FOR: acompanhar reembolso (use get_refund_status); ordem de serviço de técnico (use \
get_service_order_status); regras gerais (use search_help_center).
PARAMETERS: protocol = código como o cliente informou (ex.: ATD-1A2B3C4D).
CONFIRMATION: não requer.
RESULT: tipo, status e prazo; repasse sem alterar.
""",
    examples=[
        "Tenho um número de protocolo, como está o andamento?",
        "Quero saber do chamado que abri semana passada",
        "O protocolo da minha mediação já teve resposta?",
        "Como está a reclamação do cupom que eu fiz?",
    ],
    keywords=["protocolo", "chamado", "andamento", "acompanhar solicitacao", "numero do protocolo"],
)
async def check_protocol_status(
    protocol: Annotated[
        str, Field(description="Código do protocolo (ex.: ATD-1A2B3C4D)", max_length=20)
    ],
) -> ToolResult:
    c = get_customer()
    code = protocol.strip().upper()
    m = PROTOCOL_RE.match(code)
    if m is None:
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"{protocol.strip()} não parece um protocolo (formato XXX-1A2B3C4D).",
            recoverable=True,
        )
    prefix = m.group(1)
    if prefix in DEDICATED:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"{code} é acompanhado por uma consulta própria, com valores e datas.",
            recoverable=False,
            suggested_tool=DEDICATED[prefix],
        )
    known = PROTOCOLS.get(code)
    if known is not None and known["customer_id"] != c["id"]:
        known = None
    if known is not None:
        result = ProtocolStatusResult(
            protocol=code,
            kind=known["kind"],
            subject=known["subject"],
            protocol_status=known["status"],
            opened_at=known["opened_at"],
            expected_by=known["expected_by"],
        )
    elif prefix in KINDS:
        kind, days = KINDS[prefix]
        result = ProtocolStatusResult(
            protocol=code,
            kind=kind,
            subject=f"Solicitação {kind}",
            protocol_status="recebido",
            expected_by=days_from_today(days),
        )
    else:
        raise ToolFailure(
            "NOT_FOUND", f"Protocolo {code} não encontrado para este cliente.", recoverable=True
        )
    when = f", previsão {result.expected_by}" if result.expected_by else ""
    return ok(
        result,
        f"Protocolo {code} ({result.kind}): {result.subject}; status {result.protocol_status}"
        f"{when}.",
    )
