---
name: assinaturas
description: Assinaturas de entrega recorrente (clubes e planos mensais) — consulta, pausa, cancelamento, data da próxima entrega, itens e forma de pagamento da assinatura.
allowed-tools:
  - get_subscription
  - pause_subscription
  - cancel_subscription
  - change_subscription_date
  - change_subscription_items
  - update_subscription_payment
examples:
  - "Como está minha assinatura do clube?"
  - "Quero pular a entrega deste mês"
  - "Quero encerrar minha assinatura"
  - "Prefiro receber a assinatura em outro dia"
  - "Quero pagar a assinatura com outro cartão"
---

# Assinaturas

## Cenários e tool certa

| O cliente quer... | Tool |
|---|---|
| ver status, itens, próxima entrega, valor | get_subscription |
| parar por 1 a 3 ciclos sem cancelar | pause_subscription |
| encerrar a assinatura | cancel_subscription |
| mudar o dia da próxima entrega | change_subscription_date |
| incluir, remover ou mudar quantidade de item | change_subscription_items |
| trocar o cartão ou a forma de pagamento | update_subscription_payment |

## Heurística de desambiguação

- Cancelar: assinatura ou plano recorrente → cancel_subscription; pedido avulso ainda não enviado → cancel_order; instalação ou visita técnica → cancel_service_order. "Cancelar a entrega deste mês" é pausa (pause_subscription), não cancelamento.
- Mudar a data: próxima entrega da assinatura → change_subscription_date; pedido avulso em trânsito → reschedule_delivery; dia do técnico → reschedule_technical_visit.
- Pausar × cancelar: "dar um tempo", "pular", "viajar" → pause_subscription; "não quero mais" → cancel_subscription.
- Pagamento: cobrança da assinatura → update_subscription_payment; pagamento de pedido avulso → get_payment_status.

## Sequências típicas

1. Cliente com mais de uma assinatura e sem número: chame sem subscription_id; o erro lista as opções em details.options.
2. Alteração recusada porque a assinatura está pausada ou cancelada → get_subscription para mostrar o status.
3. update_subscription_payment com cartão: peça só o final do cartão; se não bater, o erro lista os finais conhecidos.

## Anti-padrões

- Não cancele quando o cliente pediu para pular uma entrega.
- Não peça número completo de cartão.
- Não invente a data da próxima entrega; use next_delivery.
