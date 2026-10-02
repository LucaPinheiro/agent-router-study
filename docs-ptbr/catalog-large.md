# Catálogo grande (fase 2, `CATALOG_PROFILE=large`)

> Tradução pt-BR de [`docs/catalog-large.md`](../docs/catalog-large.md). Em caso de divergência, vale o original em inglês.

O perfil grande do servidor MCP serve **62 tools em 10 skills mais 5 globais**. Ele cobre o
pós-venda de e-commerce em pt-BR e um domínio adjacente: os serviços financeiros da loja (programa
de fidelidade e cartão da loja). Existe para testar o roteamento num catálogo cerca de 3.4× o da
fase 1, com tools confundíveis desenhadas de propósito. O catálogo da fase 1 (`small`, 18 tools)
não mudou e continua sendo o padrão: mesmo `tools_list.json`, catalog hash `128584617807`.

| | pequeno (fase 1) | grande (fase 2) |
|---|---|---|
| Tools | 18 (15 + 3 globais) | 62 (57 + 5 globais) |
| Skills | 3 | 10 |
| Servidor | `uvicorn mcp_server.app:app --port 8765` | `CATALOG_PROFILE=large uvicorn mcp_server.app:app --port 8766` |
| Serviço do compose | `mcp-server` (8765) | `mcp-server-large` (8766) |
| Export | `mcp_server/tools_list.json` | `mcp_server/tools_list_large.json` |
| Mock DB | `mock_db.json` | `mock_db_large.json` (= DB pequeno + entidades novas) |
| Instruções / políticas | `instructions.md`, `policies.json` | `instructions_large.md`, `policies_large.json` |

Contagem: 3 skills originais × 5 tools (15) + 7 skills novas × 6 tools (42) + 5 globais = **62**.

## 1. Skills e tools

| # | Skill (id) | Tools | Sobreposição deliberada (confundível com) |
|---|---|---|---|
| 1 | `pedidos_logistica` (orig) | get_order_status, track_shipment, update_delivery_address, reschedule_delivery, cancel_order | – (sem mudança) |
| 2 | `pagamentos_reembolsos` (orig) | get_payment_status, generate_boleto_second_copy, request_refund, get_refund_status, dispute_charge | – |
| 3 | `trocas_devolucoes` (orig) | check_return_eligibility, create_return_request, generate_return_label, create_exchange, open_warranty_claim | – |
| 4 | `assistencia_tecnica` | schedule_installation, request_technical_visit, reschedule_technical_visit, get_service_order_status, cancel_service_order, check_extended_warranty | open_warranty_claim, reschedule_delivery, cancel_order |
| 5 | `marketplace_vendedores` | get_seller_info, contact_seller, track_seller_shipment, open_seller_mediation, report_seller_issue, rate_seller | track_shipment, dispute_charge, create_return_request |
| 6 | `assinaturas` (entrega recorrente) | get_subscription, pause_subscription, cancel_subscription, change_subscription_date, change_subscription_items, update_subscription_payment | cancel_order, reschedule_delivery, get_payment_status |
| 7 | `notas_fiscais_cadastro` | get_invoice, resend_invoice, request_invoice_correction, issue_return_invoice, get_purchase_receipt, update_billing_data | get_payment_status, create_return_request, update_delivery_address |
| 8 | `promocoes_precos` | validate_coupon, report_coupon_not_applied, get_promotion_terms, request_price_protection, get_gift_card_balance, redeem_gift_card | request_refund, dispute_charge |
| 9 | `fidelidade_cashback` (adjacente) | get_points_balance, get_points_statement, redeem_points, claim_missing_points, get_cashback_status, get_loyalty_tier | get_refund_status, get_gift_card_balance |
| 10 | `cartao_loja_crediario` (adjacente) | get_card_bill, generate_card_bill_copy, contest_card_transaction, request_limit_increase, block_store_card, renegotiate_debt | generate_boleto_second_copy, dispute_charge, get_payment_status |
| G | globais | get_customer_profile, search_help_center, escalate_to_human (orig) + update_contact_info, check_protocol_status | update_billing_data / update_delivery_address; get_service_order_status / get_refund_status |

Tools irreversíveis (destrutivas): cancel_order e dispute_charge (orig), cancel_subscription,
cancel_service_order, block_store_card. Nenhuma tool pede confirmação (`confirmation=none`, como
na fase 1).

## 2. Grupos confundíveis e onde fica cada regra

Cada grupo vira um grupo `ambiguo` no dev-L / test-L. Cada um tem uma regra de desambiguação: um
item numa seção "Heurística de desambiguação" de um SKILL.md que nomeia todas as tools do grupo.
`mcp_server/tests/test_mcp_tools_large.py::test_every_confusable_group_has_a_skill_rule` confere
isso.

| Grupo | Gatilho | Tools confundíveis | Regra (SKILL.md, item) |
|---|---|---|---|
| G1 | "cobrança errada" | dispute_charge / contest_card_transaction / open_seller_mediation | `cartao_loja_crediario` "Cobrança errada"; `marketplace_vendedores` "Cobrança errada" |
| G2 | "2ª via" | generate_boleto_second_copy / generate_card_bill_copy / get_card_bill | `cartao_loja_crediario` "2ª via" |
| G3 | "o dinheiro/crédito não caiu" | get_refund_status / get_cashback_status / claim_missing_points | `fidelidade_cashback` "O dinheiro ou crédito não caiu" |
| G4 | "cancelar" | cancel_order / cancel_subscription / cancel_service_order | `assinaturas` "Cancelar"; `assistencia_tecnica` "Cancelar" |
| G5 | "mudar a data" | reschedule_delivery / change_subscription_date / reschedule_technical_visit | `assinaturas` "Mudar a data"; `assistencia_tecnica` "Mudar a data" |
| G6 | "onde está" | track_shipment / track_seller_shipment | `marketplace_vendedores` "Onde está" |
| G7 | "defeito" | open_warranty_claim / request_technical_visit / check_extended_warranty | `assistencia_tecnica` "Defeito" |
| G8 | "mudar meus dados" | update_delivery_address / update_billing_data / update_contact_info | `notas_fiscais_cadastro` "Mudar meus dados" |
| G9 | "baixou o preço" | request_price_protection / request_refund | `promocoes_precos` "Baixou o preço" |
| G10 | "devolver produto de vendedor parceiro/PJ" | create_return_request / issue_return_invoice / open_seller_mediation | `notas_fiscais_cadastro` "Devolver produto"; `marketplace_vendedores` "Devolver produto de vendedor parceiro" |
| G11 | "comprovante" | get_payment_status / get_purchase_receipt / get_invoice | `notas_fiscais_cadastro` "Comprovante" |
| G12 | "cupom/vale" | validate_coupon / report_coupon_not_applied / redeem_gift_card | `promocoes_precos` "Cupom ou vale" |

## 3. Regras de desenho

- **As originais mantêm o código.** As 18 tools originais são os objetos da fase 1.
  `mcp_server/src/mcp_server/large/overrides.py` serve *cópias* delas só no perfil grande, e cada
  cópia:
  - acrescenta ponteiros NÃO USE PARA para as irmãs novas (`POINTERS`). As tools novas apontam
    para as originais, então sem essa camada o catálogo ficaria de um lado só;
  - corrige as duas afirmações que o catálogo grande torna falsas (`REPLACE`, `EXAMPLES`).
    escalate_to_human listava "preços, nota fiscal" como fora de escopo, e um dos seus exemplos
    era uma correção de nota fiscal, que agora é `request_invoice_correction`;
  - religa search_help_center aos artigos de política do perfil grande: a mesma pontuação e o
    mesmo schema, com 10 artigos a mais.

  Schemas, anotações e as outras chaves de `_meta` são os das originais. Um teste confere que a
  camada só *acrescenta* ponteiros. Os 3 SKILL.md originais são servidos sem alteração, e as regras
  entre skills ficam nos 7 playbooks novos e em `instructions_large.md`.
- **As tools novas seguem o estilo da casa da fase 1.** Isso significa:
  - uma descrição em pt-BR com WHEN TO USE / DON'T USE FOR / PARAMETERS / CONFIRMATION / RESULT;
  - 4 exemplos e keywords em `_meta` cada;
  - schemas de saída `oneOf` completed | error com os `$defs` compartilhados;
  - quatro anotações honestas;
  - erros de negócio como `isError` + `{code, recoverable, suggested_tool}`;
  - ids de entidade opcionais. Um id omitido resolve para a única entidade do cliente; com
    várias, a tool devolve VALIDATION_ERROR + `details.options`.

  `lint_tools_list.py --strict` reporta 62 tools, 0 erros e 0 avisos.
- **Mocks.** As tools são determinísticas e só leem o `mock_db_large.json`, que é somente leitura.
  Escritas nunca persistem e devolvem recibos derivados dos argumentos
  (`sha256(tool, customer, args)[:8]`). check_protocol_status reconhece qualquer recibo emitido por
  este servidor (tabela de prefixos), mais os protocolos abertos guardados no DB.
- **Fora de escopo** no perfil grande: vagas de emprego, lançamentos e estoque, senha e login,
  atacado. "Preços, promoções e cupons", "nota fiscal" e "alteração de cadastro" eram fora de
  escopo na fase 1 e estão **dentro do escopo** aqui. O gerador do dataset (T4.1) não deve,
  portanto, reaproveitar esses temas `fora_escopo` da fase 1 como fora de escopo do catálogo grande.

## 4. Mock DB (`mock_db_large.json`)

`mcp_server/scripts/generate_mock_db_large.py` constrói o DB grande de forma determinística. Ele
usa tabelas de estado explícitas e nenhum RNG, e rodar de novo dá um resultado idêntico byte a
byte. O DB embute o DB pequeno sem alteração, o que é verificado na importação, então os mesmos
clientes C001–C020 têm os mesmos pedidos O0001–O0060. Por cima disso, acrescenta:

- vendedores e pedidos de marketplace: 15 pedidos atendidos por 6 vendedores parceiros;
- ordens de serviço e garantias estendidas;
- 11 assinaturas;
- notas fiscais: uma NF-e por pedido enviado, mais perfis de faturamento (4 clientes CNPJ);
- cupons, promoções, preços atuais e vales-presente;
- contas de fidelidade com extratos, e cashback via Pix;
- 7 cartões da loja com faturas e transações;
- protocolos abertos.

`MOCK_DB_NOTES_LARGE.md` lista o arquétipo de cada entidade e as suas `compatible_tools`
**medidas**. O gerador chama toda tool nova com argumentos canônicos em toda entidade, no próprio
processo. O gerador do dataset só oferece uma entidade para uma tool alvo se ela estiver listada
ali. Toda tool nova completa em pelo menos 2 entidades.

## 5. Checklist de revisão (T3.1 / T3.2)

- [x] 62 tools: `tools_list_large.json` passa no lint (0 erros, 0 avisos, `--strict`).
- [x] Todo grupo G1–G12 tem uma regra num SKILL.md (`test_every_confusable_group_has_a_skill_rule`, 12/12).
- [x] As `allowed-tools` das skills batem com a skill em `_meta` das tools. Isso é conferido pelo
  `fetch_catalog` do host (`tests/test_catalog_large.py`) e pelo teste de resources do MCP, nos
  dois perfis.
- [x] Toda tool nova completa em pelo menos uma entidade do mock (`test_every_new_tool_completes_on_some_mock_entity`).
- [x] Toda tool nova tem pelo menos um caso de erro de negócio com code + suggested_tool
  verificados (`test_new_tool_business_error`, 63 casos).
- [x] Sem becos sem saída: todo `suggested_tool` consegue completar. Tools de leitura nunca sugerem
  uma ação irreversível. Os dois perfis rodam os testes de consistência da fase 1, com as tools
  novas incluídas no grande.
- [x] Vazamento: nenhum exemplo novo (tool `_meta`, camada, frontmatter de SKILL.md) é igual a, ou
  está contido em, um turno de usuário dos splits dev, test-v1 ou test-v2 da fase 1.
- [x] Perfil pequeno: `tools_list.json` é idêntico byte a byte e o catalog hash é `128584617807`
  (offline e no processo).
