---
name: promocoes_precos
description: Promoções, preços e vales — validação de cupom, cupom não aplicado em compra feita, regulamento de campanhas, proteção de preço quando o valor baixa, saldo e resgate de vale-presente.
allowed-tools:
  - validate_coupon
  - report_coupon_not_applied
  - get_promotion_terms
  - request_price_protection
  - get_gift_card_balance
  - redeem_gift_card
examples:
  - "Esse código de desconto ainda funciona?"
  - "O desconto do cupom não entrou na minha compra"
  - "Quais as regras da promoção da semana?"
  - "O preço baixou logo depois que eu comprei"
  - "Ganhei um vale-presente, como uso?"
---

# Promoções, preços e vales

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| saber se um cupom vale e suas regras | validate_coupon |
| desconto de cupom que não entrou numa compra feita | report_coupon_not_applied |
| regulamento e período de uma campanha | get_promotion_terms |
| diferença quando o preço caiu após a compra | request_price_protection |
| saldo e validade de vales já na conta | get_gift_card_balance |
| ativar um vale-presente recebido | redeem_gift_card |

## Heurística de desambiguação

- Cupom ou vale: código de desconto antes de comprar → validate_coupon; cupom que não foi descontado numa compra já feita → report_coupon_not_applied; vale-presente ou cartão-presente recebido → redeem_gift_card (e depois get_gift_card_balance para o saldo).
- Baixou o preço: produto ficou mais barato em até 15 dias da compra → request_price_protection (crédito em vale); dinheiro de pedido cancelado ou extraviado → request_refund. Se o cliente quer desistir do produto, é devolução (create_return_request), não proteção de preço.
- Regulamento × regra geral: campanha com nome ou cupom → get_promotion_terms; prazo de troca, entrega ou reembolso → search_help_center.
- Vale × pontos × cashback: vale-presente → get_gift_card_balance; pontos do programa → get_points_balance; cashback → get_cashback_status.

## Sequências típicas

1. report_coupon_not_applied recusado porque o cupom não valia para o pedido → validate_coupon explica as regras.
2. get_gift_card_balance recusado porque o vale não foi resgatado → redeem_gift_card.
3. request_price_protection gera um vale-compra: o código vem em gift_card_code.

## Anti-padrões

- Não prometa desconto antes de validate_coupon.
- Não trate vale-presente como cupom: são códigos diferentes.
- Não altere o código do vale ou do cupom.
