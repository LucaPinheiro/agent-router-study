---
name: trocas_devolucoes
description: Pós-entrega — elegibilidade de devolução, troca ou garantia, abertura de devolução, etiqueta de postagem, troca por outro tamanho/cor e acionamento de garantia.
allowed-tools:
  - check_return_eligibility
  - create_return_request
  - generate_return_label
  - create_exchange
  - open_warranty_claim
examples:
  - "O tênis veio no tamanho errado"
  - "Quero devolver o produto que recebi"
  - "Preciso da etiqueta para devolver"
  - "Ainda dá tempo de trocar?"
  - "Meu fone parou de funcionar depois de 3 meses"
---

# Trocas e devoluções

## Prazos (contados da entrega)

- Arrependimento: 7 dias → create_return_request com reason=arrependimento.
- Defeito, avaria, produto errado, tamanho errado: 30 dias → create_return_request (dinheiro de volta) ou create_exchange (outro tamanho/cor).
- Defeito após 30 dias e até 12 meses → open_warranty_claim.

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| saber se ainda pode devolver/trocar | check_return_eligibility |
| devolver e receber o dinheiro | create_return_request |
| etiqueta para postar a devolução | generate_return_label |
| outro tamanho, cor ou variação | create_exchange |
| conserto ou análise de defeito tardio | open_warranty_claim |

## Heurística de desambiguação

- Troca × devolução: "quero outro número/cor" é create_exchange; "quero meu dinheiro de volta" é create_return_request.
- Devolução × cancelamento: produto já entregue é devolução; pedido não enviado é cancel_order (skill pedidos_logistica).
- Devolução × reembolso: se o produto nunca chegou (extraviado), não há o que devolver → request_refund (skill pagamentos_reembolsos).
- Defeito: até 30 dias é devolução ou troca; depois, garantia. Prazo incerto → check_return_eligibility primeiro.

## Sequências típicas

1. create_return_request → generate_return_label (com o return_id retornado, ou order_id).
2. Recusa NOT_ELIGIBLE por prazo em defeito → siga suggested_tool (open_warranty_claim).
3. Pedido com vários itens: sem sku, a tool devolve as opções em details.options.

## Anti-padrões

- Não abra devolução para pedido ainda em trânsito.
- Não troque o motivo informado pelo cliente para caber no prazo.
