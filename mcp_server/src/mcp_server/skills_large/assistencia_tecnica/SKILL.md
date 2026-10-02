---
name: assistencia_tecnica
description: Assistência técnica de produtos entregues — instalação de eletrodomésticos, visita técnica em casa para defeito, remarcação e cancelamento de ordem de serviço, acompanhamento da OS e consulta de garantia estendida.
allowed-tools:
  - schedule_installation
  - request_technical_visit
  - reschedule_technical_visit
  - get_service_order_status
  - cancel_service_order
  - check_extended_warranty
examples:
  - "Quero agendar a instalação do eletrodoméstico que recebi"
  - "A cafeteira parou, vocês mandam técnico?"
  - "O técnico vem amanhã mesmo?"
  - "Preciso mudar o dia da visita técnica"
  - "Até quando vai a garantia estendida do meu aparelho?"
---

# Assistência técnica

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| instalar um eletrodoméstico entregue | schedule_installation |
| técnico em casa para eletrodoméstico com defeito | request_technical_visit |
| mudar o dia ou o período da instalação ou visita | reschedule_technical_visit |
| saber quando o técnico vem, status da OS | get_service_order_status |
| desistir da instalação ou visita agendada | cancel_service_order |
| saber se tem garantia estendida e até quando | check_extended_warranty |

## Heurística de desambiguação

- Defeito: eletrodoméstico que precisa de técnico em casa → request_technical_visit; produto portátil enviado para análise entre 30 dias e 12 meses da entrega → open_warranty_claim (skill trocas_devolucoes); só quer saber a cobertura ou a validade → check_extended_warranty. Na dúvida sobre a cobertura, consulte check_extended_warranty primeiro.
- Defeito em até 30 dias da entrega é devolução ou troca (create_return_request ou create_exchange), não assistência.
- Instalação × visita: produto novo funcionando → schedule_installation; produto com problema → request_technical_visit.
- Mudar a data: dia do técnico → reschedule_technical_visit; entrega de pedido em trânsito → reschedule_delivery; próxima entrega da assinatura → change_subscription_date.
- Cancelar: instalação ou visita → cancel_service_order; pedido não enviado → cancel_order; assinatura → cancel_subscription.
- Acompanhar: ordem de serviço (OS-...) → get_service_order_status; outros protocolos → check_protocol_status.

## Sequências típicas

1. request_technical_visit recusado porque o item não é eletrodoméstico → siga suggested_tool (open_warranty_claim ou check_extended_warranty).
2. schedule_installation ou request_technical_visit recusado porque já existe OS → get_service_order_status, depois reschedule_technical_visit se o cliente quiser outra data.
3. Cliente com várias OS e sem número: chame sem service_order_id; o erro lista as opções em details.options.

## Anti-padrões

- Não abra visita técnica para defeito de produto recém-entregue que cabe em troca.
- Não invente data de visita; use scheduled_for do resultado.
- Não cancele a OS quando o cliente só quer outro dia.
