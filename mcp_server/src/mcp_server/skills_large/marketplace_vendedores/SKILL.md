---
name: marketplace_vendedores
description: Compras de vendedores parceiros (marketplace) — dados e reputação do vendedor, mensagem ao vendedor, rastreio do envio feito pelo vendedor, mediação da loja, denúncia e avaliação do vendedor.
allowed-tools:
  - get_seller_info
  - contact_seller
  - track_seller_shipment
  - open_seller_mediation
  - report_seller_issue
  - rate_seller
examples:
  - "Quem vendeu o produto que comprei?"
  - "Quero mandar uma mensagem para o lojista"
  - "O vendedor parceiro já despachou?"
  - "O lojista não resolve meu problema"
  - "Quero avaliar a loja parceira"
---

# Vendedores parceiros (marketplace)

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| saber quem vendeu, CNPJ, reputação | get_seller_info |
| perguntar algo ao vendedor | contact_seller |
| rastrear o envio feito pelo vendedor | track_seller_shipment |
| que a loja intervenha num problema com o vendedor | open_seller_mediation |
| denunciar anúncio enganoso, falsificação ou conduta | report_seller_issue |
| dar nota ao vendedor | rate_seller |

## Heurística de desambiguação

- Onde está: pedido enviado pelo vendedor parceiro → track_seller_shipment; pedido vendido e entregue pela loja → track_shipment (skill pedidos_logistica). Se não souber quem vendeu, get_seller_info responde; a recusa de track_seller_shipment também aponta track_shipment.
- Cobrança errada: compra de vendedor parceiro cobrada a mais ou indevidamente → open_seller_mediation; cobrança não reconhecida em cartão de banco de um pedido da loja → dispute_charge; lançamento no cartão da loja → contest_card_transaction.
- Devolver produto de vendedor parceiro: primeiro create_return_request como qualquer devolução; se o vendedor recusou a devolução → open_seller_mediation; compra com CNPJ que exige nota → issue_return_invoice.
- Falar × mediar × denunciar: primeira conversa → contact_seller; vendedor não resolveu ou não respondeu → open_seller_mediation; só registrar má conduta, sem pedir solução → report_seller_issue.

## Sequências típicas

1. contact_seller → sem resposta no prazo → open_seller_mediation(reason=sem_resposta).
2. open_seller_mediation recusado porque já existe mediação → check_protocol_status com o protocolo em details.protocol.
3. rate_seller recusado porque o pedido não foi entregue → track_seller_shipment.

## Anti-padrões

- Não use dispute_charge para problemas com vendedor parceiro.
- Não repasse dados do cartão ao vendedor em contact_seller.
- Não abra mediação antes de entender se a compra é mesmo de vendedor parceiro.
