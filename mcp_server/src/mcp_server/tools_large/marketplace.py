"""Skill marketplace_vendedores: get_seller_info, contact_seller, track_seller_shipment,
open_seller_mediation, report_seller_issue, rate_seller."""

from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastmcp.tools.base import ToolResult
from pydantic import Field

from mcp_server.core import READ, TODAY, WRITE, ToolFailure, days_from_today, ok, protocol
from mcp_server.large.data import PROTOCOLS, SELLERS, SLA, large_tool, marketplace_order
from mcp_server.large.models import (
    SellerContactResult,
    SellerInfoResult,
    SellerMediationResult,
    SellerRatingResult,
    SellerReportResult,
    SellerShipmentResult,
)
from mcp_server.models import ShipmentEvent

SKILL = "marketplace_vendedores"
OrderId = Annotated[
    str | None,
    Field(description="Número do pedido (ex.: O0001). Omita se o cliente tem um só pedido"),
]


@large_tool(
    skill=SKILL,
    scope="marketplace:read",
    title="Dados do vendedor parceiro",
    annotations=READ,
    result=SellerInfoResult,
    description="""
Mostra quem vendeu um pedido de vendedor parceiro (marketplace): nome, CNPJ mascarado, \
reputação e prazo de resposta.
WHEN TO USE: "quem é o vendedor do meu pedido?", "essa loja parceira é confiável?", antes de \
falar com o vendedor.
DON'T USE FOR: status do pedido (use get_order_status); falar com o vendedor (use \
contact_seller); dados do meu cadastro (use get_customer_profile).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: dados públicos do vendedor; repasse sem alterar.
""",
    examples=[
        "Quem é o vendedor que me vendeu esse produto?",
        "Essa loja parceira tem boa reputação?",
        "Meu pedido foi vendido por outra empresa?",
        "Qual o CNPJ do lojista que vendeu minha jaqueta?",
    ],
    keywords=["vendedor", "lojista", "parceiro", "marketplace", "quem vendeu", "reputacao"],
)
async def get_seller_info(order_id: OrderId = None) -> ToolResult:
    o, mk = marketplace_order(order_id)
    s = SELLERS[mk["seller_id"]]
    result = SellerInfoResult(
        order_id=o["id"],
        seller_id=s["id"],
        seller_name=s["name"],
        cnpj_masked=s["cnpj_masked"],
        rating=s["rating"],
        ratings_count=s["ratings_count"],
        response_hours=s["response_hours"],
        seller_status=s["status"],
    )
    return ok(
        result,
        f"O pedido {o['id']} foi vendido por {s['name']} (CNPJ {s['cnpj_masked']}), nota "
        f"{s['rating']} em {s['ratings_count']} avaliações; responde em até "
        f"{s['response_hours']} horas.",
    )


@large_tool(
    skill=SKILL,
    scope="marketplace:write",
    title="Enviar mensagem ao vendedor",
    annotations=WRITE,
    result=SellerContactResult,
    description="""
Envia uma mensagem do cliente ao vendedor parceiro de um pedido, pelo canal da loja, com \
protocolo e prazo de resposta.
WHEN TO USE: "quero perguntar ao vendedor", "preciso falar com a loja que me vendeu", dúvida \
sobre produto ou envio do vendedor.
DON'T USE FOR: quando o vendedor não resolveu ou não respondeu (use open_seller_mediation); \
denunciar o vendedor (use report_seller_issue); falar com um atendente da loja (use \
escalate_to_human).
PARAMETERS: message = a mensagem do cliente, sem dados de cartão; order_id opcional se o \
cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: protocolo e prazo de resposta do vendedor; repasse sem alterar.
""",
    examples=[
        "Quero mandar uma pergunta para o vendedor do meu pedido",
        "Como falo com a loja parceira que me vendeu?",
        "Pergunta ao lojista se a nota vem junto com o produto",
        "Preciso combinar a entrega direto com o vendedor",
    ],
    keywords=["falar com vendedor", "mensagem", "contato lojista", "perguntar ao vendedor"],
)
async def contact_seller(
    message: Annotated[
        str, Field(description="Mensagem do cliente ao vendedor", min_length=3, max_length=1000)
    ],
    order_id: OrderId = None,
) -> ToolResult:
    o, mk = marketplace_order(order_id)
    s = SELLERS[mk["seller_id"]]
    proto = protocol("MSG", "contact_seller", {"order_id": o["id"], "message": message})
    respond_by = (
        (datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=s["response_hours"]))
        .date()
        .isoformat()
    )
    result = SellerContactResult(
        order_id=o["id"], seller_id=s["id"], protocol=proto, respond_by=respond_by
    )
    return ok(
        result,
        f"Mensagem enviada a {s['name']} sobre o pedido {o['id']}. Protocolo {proto}; resposta "
        f"até {respond_by}.",
    )


@large_tool(
    skill=SKILL,
    scope="marketplace:read",
    title="Rastrear envio do vendedor",
    annotations=READ,
    result=SellerShipmentResult,
    description="""
Rastreia o envio feito pelo próprio vendedor parceiro: transportadora do vendedor, código e \
eventos.
WHEN TO USE: "cadê o produto que comprei de um vendedor parceiro?", "o lojista já postou?".
DON'T USE FOR: pedido vendido e entregue pela loja (use track_shipment); status geral do \
pedido (use get_order_status); vendedor que não envia e não responde (use \
open_seller_mediation).
PARAMETERS: order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: eventos em ordem cronológica; repasse códigos e datas sem alterar.
""",
    examples=[
        "O vendedor parceiro já postou minha compra?",
        "Qual o rastreio do produto que veio de outra loja pelo site?",
        "Comprei de um lojista do marketplace, onde está o pacote?",
        "O vendedor disse que enviou, como acompanho?",
    ],
    keywords=["rastreio vendedor", "postou", "envio do lojista", "marketplace", "rastrear"],
)
async def track_seller_shipment(order_id: OrderId = None) -> ToolResult:
    o, mk = marketplace_order(order_id)
    s = SELLERS[mk["seller_id"]]
    result = SellerShipmentResult(
        order_id=o["id"],
        seller_id=s["id"],
        carrier=mk["seller_carrier"],
        tracking_code=mk["seller_tracking_code"],
        shipment_status=mk["seller_shipment_status"],
        eta=mk["eta"],
        events=[ShipmentEvent(**e) for e in mk["events"]],
    )
    if not mk["events"]:
        text = (
            f"O vendedor {s['name']} ainda não postou o pedido {o['id']}; previsão de entrega "
            f"{mk['eta']}."
        )
    else:
        last = mk["events"][-1]
        text = (
            f"Pedido {o['id']} enviado por {s['name']} via {mk['seller_carrier']}, rastreio "
            f"{mk['seller_tracking_code']}, status {mk['seller_shipment_status']}, previsão "
            f"{mk['eta']}. Último evento em {last['at']}: {last['description']}."
        )
    return ok(result, text)


@large_tool(
    skill=SKILL,
    scope="marketplace:write",
    title="Abrir mediação com vendedor",
    annotations=WRITE,
    result=SellerMediationResult,
    description="""
Abre a mediação da loja num problema com vendedor parceiro: não entregou, produto diferente, \
devolução recusada, cobrança indevida ou vendedor sem resposta.
WHEN TO USE: "o vendedor não resolve", "o lojista recusou minha devolução", "comprei de \
parceiro e me cobraram errado".
DON'T USE FOR: produto vendido pela loja (use create_return_request ou dispute_charge); \
primeira dúvida ao vendedor (use contact_seller); denúncia sem pedir solução (use \
report_seller_issue).
PARAMETERS: reason = nao_entregue | produto_diferente | devolucao_recusada | cobranca_indevida \
| sem_resposta; details opcional.
CONFIRMATION: não requer.
RESULT: id da mediação e prazo; repasse sem alterar.
""",
    examples=[
        "O vendedor parceiro recusou minha devolução, preciso de ajuda da loja",
        "O lojista não responde há dias e o produto não chegou",
        "O vendedor do marketplace me mandou um produto diferente e não resolve",
        "Quero que a loja interceda no problema com o vendedor",
    ],
    keywords=["mediacao", "vendedor nao resolve", "lojista recusou", "intermediar", "disputa"],
)
async def open_seller_mediation(
    reason: Annotated[
        Literal[
            "nao_entregue",
            "produto_diferente",
            "devolucao_recusada",
            "cobranca_indevida",
            "sem_resposta",
        ],
        Field(description="Motivo da mediação"),
    ],
    order_id: OrderId = None,
    details: Annotated[
        str | None, Field(description="Detalhes ditos pelo cliente, se houver", max_length=500)
    ] = None,
) -> ToolResult:
    o, mk = marketplace_order(order_id)
    existing = next(
        (
            p
            for p in PROTOCOLS.values()
            if p["kind"] == "mediacao_vendedor" and p["order_id"] == o["id"]
        ),
        None,
    )
    if existing is not None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Já existe a mediação {existing['id']} ({existing['status']}) para o pedido "
            f"{o['id']}.",
            recoverable=False,
            suggested_tool="check_protocol_status",
            details={"protocol": existing["id"]},
        )
    mediation_id = protocol(
        "MED", "open_seller_mediation", {"order_id": o["id"], "reason": reason, "details": details}
    )
    until = days_from_today(SLA["seller_mediation_resolution_days"])
    result = SellerMediationResult(
        order_id=o["id"],
        seller_id=mk["seller_id"],
        mediation_id=mediation_id,
        reason=reason,
        expected_resolution_by=until,
    )
    return ok(
        result,
        f"Mediação {mediation_id} aberta com {SELLERS[mk['seller_id']]['name']} sobre o pedido "
        f"{o['id']} (motivo {reason}). Resposta da loja até {until}.",
    )


@large_tool(
    skill=SKILL,
    scope="marketplace:write",
    title="Denunciar vendedor",
    annotations=WRITE,
    result=SellerReportResult,
    description="""
Registra uma denúncia contra um vendedor parceiro (anúncio enganoso, produto falsificado, \
conduta inadequada) para a equipe de qualidade, sem abrir disputa do pedido.
WHEN TO USE: "quero denunciar esse vendedor", "o anúncio era enganoso", "suspeito de produto \
falsificado".
DON'T USE FOR: resolver o problema do pedido (use open_seller_mediation); dar nota ao \
vendedor (use rate_seller); reclamar da própria loja (use escalate_to_human).
PARAMETERS: issue_type = anuncio_enganoso | produto_falsificado | conduta | outro; details = \
relato do cliente; order_id opcional se o cliente tem um só pedido.
CONFIRMATION: não requer.
RESULT: id da denúncia; repasse sem alterar.
""",
    examples=[
        "Quero denunciar o vendedor, o anúncio era enganoso",
        "Acho que o lojista vende produto falsificado",
        "O vendedor foi grosseiro comigo, quero registrar uma queixa contra ele",
        "Como reporto uma loja parceira suspeita?",
    ],
    keywords=["denunciar", "denuncia", "falsificado", "enganoso", "reportar vendedor"],
)
async def report_seller_issue(
    issue_type: Annotated[
        Literal["anuncio_enganoso", "produto_falsificado", "conduta", "outro"],
        Field(description="Tipo de denúncia"),
    ],
    details: Annotated[str, Field(description="Relato do cliente", min_length=3, max_length=1000)],
    order_id: OrderId = None,
) -> ToolResult:
    o, mk = marketplace_order(order_id)
    report_id = protocol(
        "DEN",
        "report_seller_issue",
        {"seller_id": mk["seller_id"], "issue_type": issue_type, "details": details},
    )
    result = SellerReportResult(
        seller_id=mk["seller_id"], report_id=report_id, issue_type=issue_type
    )
    return ok(
        result,
        f"Denúncia {report_id} registrada contra {SELLERS[mk['seller_id']]['name']} "
        f"({issue_type}). Análise em até {SLA['seller_report_review_days']} dias.",
    )


@large_tool(
    skill=SKILL,
    scope="marketplace:write",
    title="Avaliar vendedor",
    annotations=WRITE,
    result=SellerRatingResult,
    description="""
Registra a nota (1 a 5) e o comentário do cliente sobre o vendedor parceiro de um pedido \
entregue.
WHEN TO USE: "quero avaliar o vendedor", "dar nota para a loja parceira".
DON'T USE FOR: denúncia (use report_seller_issue); problema não resolvido (use \
open_seller_mediation).
PARAMETERS: rating = inteiro de 1 a 5; comment opcional; order_id opcional se o cliente tem \
um só pedido.
CONFIRMATION: não requer.
RESULT: protocolo da avaliação; repasse sem alterar.
""",
    examples=[
        "Quero dar nota 5 para o vendedor, chegou rapidinho",
        "Como avalio a loja parceira que me vendeu?",
        "Vou deixar uma avaliação ruim para esse vendedor",
        "Quero registrar minha opinião sobre o lojista",
    ],
    keywords=["avaliar", "nota", "avaliacao", "estrelas", "opiniao sobre vendedor"],
)
async def rate_seller(
    rating: Annotated[int, Field(description="Nota de 1 a 5", ge=1, le=5)],
    order_id: OrderId = None,
    comment: Annotated[
        str | None, Field(description="Comentário do cliente, se houver", max_length=500)
    ] = None,
) -> ToolResult:
    o, mk = marketplace_order(order_id)
    if mk["seller_shipment_status"] != "delivered":
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} ainda não foi entregue pelo vendedor; a avaliação abre após a "
            "entrega.",
            recoverable=False,
            suggested_tool="track_seller_shipment",
        )
    if mk["rating"] is not None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O vendedor do pedido {o['id']} já foi avaliado com nota {mk['rating']}.",
            recoverable=False,
        )
    proto = protocol(
        "AVL", "rate_seller", {"order_id": o["id"], "rating": rating, "comment": comment}
    )
    result = SellerRatingResult(
        order_id=o["id"], seller_id=mk["seller_id"], rating=rating, protocol=proto
    )
    return ok(
        result,
        f"Avaliação nota {rating} registrada para {SELLERS[mk['seller_id']]['name']} (pedido "
        f"{o['id']}). Protocolo {proto}.",
    )
