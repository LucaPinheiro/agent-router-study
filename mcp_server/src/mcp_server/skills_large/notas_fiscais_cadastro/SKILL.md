---
name: notas_fiscais_cadastro
description: Notas fiscais, comprovantes e dados de faturamento — consulta e reenvio da NF-e, carta de correção, nota de devolução para compras com CNPJ, comprovante de compra e atualização dos dados de faturamento.
allowed-tools:
  - get_invoice
  - resend_invoice
  - request_invoice_correction
  - issue_return_invoice
  - get_purchase_receipt
  - update_billing_data
examples:
  - "Preciso da nota fiscal do meu pedido"
  - "A nota não chegou no meu e-mail"
  - "Meu nome saiu errado na NF"
  - "Comprei pelo CNPJ e vou devolver"
  - "Quero um comprovante da compra"
---

# Notas fiscais e cadastro

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| número, chave de acesso ou dados da NF-e | get_invoice |
| receber a NF de novo (e-mail ou WhatsApp) | resend_invoice |
| corrigir nome, endereço ou IE numa nota emitida | request_invoice_correction |
| nota fiscal de devolução (compra com CNPJ) | issue_return_invoice |
| comprovante de compra paga | get_purchase_receipt |
| dados de faturamento das próximas notas | update_billing_data |

## Heurística de desambiguação

- Comprovante: prova de que pagou (recibo, autenticação) → get_purchase_receipt; documento fiscal (NF-e, chave de acesso, DANFE) → get_invoice; só saber se o pagamento foi aprovado → get_payment_status (skill pagamentos_reembolsos).
- Mudar meus dados: endereço de entrega de pedido não enviado → update_delivery_address; nome, endereço de cobrança ou IE das próximas notas → update_billing_data; e-mail ou celular → update_contact_info. Nota já emitida com dado errado → request_invoice_correction.
- Devolver produto: compra com CPF → create_return_request (sem nota); compra com CNPJ → create_return_request e issue_return_invoice para acompanhar o produto; vendedor parceiro que recusou → open_seller_mediation.
- Nota não emitida (pedido em preparação) → get_invoice explica; a NF sai no despacho.

## Sequências típicas

1. issue_return_invoice recusado porque a compra foi com CPF → siga suggested_tool (create_return_request ou generate_return_label).
2. request_invoice_correction fora de 30 dias ou para CPF/CNPJ → escalate_to_human.
3. get_purchase_receipt recusado por pagamento pendente → get_payment_status.

## Anti-padrões

- Não altere nenhum dígito da chave de acesso.
- Não use update_billing_data para corrigir nota já emitida.
- Não peça CPF ou CNPJ ao cliente; o cadastro vem da requisição.
