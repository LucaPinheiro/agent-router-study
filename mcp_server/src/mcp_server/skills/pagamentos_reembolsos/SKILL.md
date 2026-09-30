---
name: pagamentos_reembolsos
description: Pagamentos e dinheiro de volta — status do pagamento, 2ª via de boleto, solicitação e acompanhamento de reembolso e contestação de cobrança no cartão.
allowed-tools:
  - get_payment_status
  - generate_boleto_second_copy
  - request_refund
  - get_refund_status
  - dispute_charge
examples:
  - "Meu pagamento foi aprovado?"
  - "Preciso da 2ª via do boleto"
  - "Quero meu dinheiro de volta do pedido cancelado"
  - "Meu reembolso já caiu?"
  - "Não reconheço essa cobrança no cartão"
---

# Pagamentos e reembolsos

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| saber se o pagamento foi aprovado, parcelas, vencimento | get_payment_status |
| novo boleto (vencido ou perdido) | generate_boleto_second_copy |
| dinheiro de volta de pedido cancelado sem estorno ou extraviado | request_refund |
| acompanhar um reembolso já pedido | get_refund_status |
| contestar cobrança no cartão (não reconhecida, duplicada, valor errado) | dispute_charge |

## Heurística de desambiguação

- Pagamento × reembolso: dinheiro **saindo** do cliente é get_payment_status; dinheiro **voltando** é get_refund_status.
- "Quero meu dinheiro de volta":
  - pedido ainda não enviado → cancel_order (estorno automático);
  - pedido entregue → create_return_request (o produto volta primeiro);
  - pedido cancelado sem estorno ou extraviado → request_refund.
- "Não reconheço a cobrança" ou "cobraram duas vezes" é dispute_charge, e só vale para cartão de crédito. Desistência nunca é contestação.
- Boleto pago mas pedido parado: get_payment_status mostra se compensou.

## Sequências típicas

1. request_refund recusado com "já existe reembolso" → get_refund_status.
2. generate_boleto_second_copy recusado porque o pagamento é cartão/Pix → get_payment_status.
3. dispute_charge recusado para Pix/boleto → request_refund, se o pedido estiver cancelado ou extraviado.

## Anti-padrões

- Não altere nenhum dígito da linha digitável.
- Não prometa prazo de estorno diferente do retornado (expected_by).
- Não use dispute_charge como atalho para reembolso comum: é irreversível.
