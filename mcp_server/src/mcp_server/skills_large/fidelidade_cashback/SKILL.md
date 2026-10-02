---
name: fidelidade_cashback
description: Programa de fidelidade da loja — saldo e extrato de pontos, troca de pontos, pontos de compra não creditados, cashback de compras e nível no programa.
allowed-tools:
  - get_points_balance
  - get_points_statement
  - redeem_points
  - claim_missing_points
  - get_cashback_status
  - get_loyalty_tier
examples:
  - "Quantos pontos eu tenho?"
  - "Quero ver o extrato do programa de pontos"
  - "Como troco meus pontos?"
  - "Os pontos da minha compra não apareceram"
  - "O cashback da compra já foi liberado?"
---

# Fidelidade e cashback

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| saldo, pontos pendentes e a vencer | get_points_balance |
| extrato de créditos e resgates | get_points_statement |
| trocar pontos por vale, frete ou doação | redeem_points |
| pontos de compra entregue que não caíram | claim_missing_points |
| valor e liberação do cashback de uma compra | get_cashback_status |
| nível, benefícios e quanto falta para subir | get_loyalty_tier |

## Heurística de desambiguação

- O dinheiro ou crédito não caiu: estorno de pedido cancelado, extraviado ou devolvido → get_refund_status (skill pagamentos_reembolsos); cashback de compra paga com Pix → get_cashback_status; pontos de compra entregue → claim_missing_points (antes de 7 dias da entrega os pontos ainda estão pendentes; get_points_balance mostra).
- Saldo × extrato: quanto tem → get_points_balance; de onde veio → get_points_statement.
- Trocar pontos × resgatar vale: pontos do programa → redeem_points; código de vale-presente → redeem_gift_card.
- Nível × perfil: nível e benefícios → get_loyalty_tier; dados do cadastro e pedidos → get_customer_profile.

## Sequências típicas

1. claim_missing_points recusado porque os pontos já foram creditados → get_points_statement.
2. claim_missing_points recusado porque ainda está no prazo de crédito → get_points_balance (pontos pendentes).
3. redeem_points com saldo insuficiente: o erro traz available_points; ofereça trocar esse valor.

## Anti-padrões

- Não trate cashback como reembolso: são tools diferentes.
- Não prometa crédito de pontos antes do prazo de 7 dias.
- Não troque pontos sem o cliente dizer quantos.
