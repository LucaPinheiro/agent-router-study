---
name: pedidos_logistica
description: Situação de pedidos e entregas — status do pedido, rastreio do pacote, alteração de endereço antes do envio, reagendamento de entrega em trânsito e cancelamento de pedido ainda não enviado.
allowed-tools:
  - get_order_status
  - track_shipment
  - update_delivery_address
  - reschedule_delivery
  - cancel_order
examples:
  - "Cadê minha encomenda?"
  - "Meu pedido já foi enviado?"
  - "Preciso que o pacote vá para outro endereço"
  - "Consigo escolher outra data para receber?"
  - "Quero cancelar meu pedido antes de enviarem"
---

# Pedidos e logística

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| saber a situação do pedido, itens, valor, previsão | get_order_status |
| saber onde está o pacote, código de rastreio, eventos | track_shipment |
| receber em outro endereço (pedido ainda não enviado) | update_delivery_address |
| receber em outra data (pedido já enviado, não entregue) | reschedule_delivery |
| desistir antes do envio | cancel_order |

## Heurística de desambiguação

- "Qual a situação da compra?" → get_order_status. "Cadê o pacote?" ou "está parado na transportadora" → track_shipment. Na dúvida, comece por get_order_status: ele diz se já existe envio.
- Endereço × data: mudar **onde** é update_delivery_address; mudar **quando** é reschedule_delivery.
- Cancelar × reembolso × devolução: cancel_order só vale antes do envio. Pedido entregue vai para create_return_request (skill trocas_devolucoes). Pedido cancelado sem estorno, ou extraviado, vai para request_refund (skill pagamentos_reembolsos).

## Sequências típicas

1. Cliente não informa o pedido e tem vários: chame a tool sem order_id; o erro VALIDATION_ERROR lista as opções em details.options. Pergunte qual.
2. Atraso: track_shipment. Se o status for `lost` (extraviado), o próximo passo é request_refund. Se for `delivery_failed`, ofereça reschedule_delivery.
3. Cancelamento recusado com NOT_ELIGIBLE: siga suggested_tool (create_return_request para entregue; escalate_to_human para em trânsito).

## Anti-padrões

- Não preencha o endereço novo com o endereço atual do cadastro.
- Não invente datas de entrega; use eta e estimated_delivery do resultado.
- Não chame cancel_order para pedir dinheiro de volta de pedido já cancelado.
