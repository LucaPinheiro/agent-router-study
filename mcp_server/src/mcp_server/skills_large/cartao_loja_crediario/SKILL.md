---
name: cartao_loja_crediario
description: Cartão da loja e crediário — fatura, 2ª via da fatura, contestação de lançamento, aumento de limite, bloqueio por perda ou roubo e renegociação de dívida em atraso.
allowed-tools:
  - get_card_bill
  - generate_card_bill_copy
  - contest_card_transaction
  - request_limit_increase
  - block_store_card
  - renegotiate_debt
examples:
  - "Quanto está a fatura do cartão da loja?"
  - "Preciso da segunda via da fatura do crediário"
  - "Tem uma compra que não fiz no cartão da loja"
  - "Perdi meu cartão da loja"
  - "Quero parcelar a fatura atrasada"
---

# Cartão da loja e crediário

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| ver fatura, vencimento, limite e lançamentos | get_card_bill |
| boleto (2ª via) da fatura | generate_card_bill_copy |
| contestar um lançamento da fatura | contest_card_transaction |
| mais limite | request_limit_increase |
| bloquear por perda, roubo ou fraude | block_store_card |
| parcelar fatura em atraso | renegotiate_debt |

## Heurística de desambiguação

- 2ª via: boleto de um pedido com pagamento pendente → generate_boleto_second_copy (skill pagamentos_reembolsos); boleto da fatura do cartão da loja → generate_card_bill_copy; só ver valor e vencimento da fatura → get_card_bill.
- Cobrança errada: lançamento na fatura do cartão da loja → contest_card_transaction; cobrança em cartão de banco de um pedido → dispute_charge; compra de vendedor parceiro → open_seller_mediation.
- Cartão da loja × cartão de banco: "fatura", "crediário", "limite" e "cartão da loja" são desta skill; pagamento de pedido com cartão de crédito comum é get_payment_status.
- Atraso: até 30 dias, generate_card_bill_copy com juros; acima de 30 dias, só renegotiate_debt.
- Perda ou roubo → block_store_card; lançamento suspeito isolado → contest_card_transaction.

## Sequências típicas

1. contest_card_transaction precisa do id TX-...: chame get_card_bill para listar os lançamentos.
2. generate_card_bill_copy recusado por atraso grave → renegotiate_debt.
3. request_limit_increase recusado por atraso → get_card_bill.

## Anti-padrões

- Não use dispute_charge para o cartão da loja.
- Não bloqueie o cartão quando o cliente só contesta um lançamento: o bloqueio é irreversível.
- Não altere nenhum dígito da linha digitável.
