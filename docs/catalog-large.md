# Large catalog (phase 2, `CATALOG_PROFILE=large`)

The large profile of the MCP server serves **62 tools in 10 skills plus 5 globals**. It covers
pt-BR e-commerce post-sales and an adjacent domain: the store's financial services (loyalty
program and store card). It exists to test routing on a catalog about 3.4× the phase-1 one, with
deliberately designed confusable tools. The phase-1 catalog (`small`, 18 tools) is unchanged and
stays the default: same `tools_list.json`, catalog hash `128584617807`.

| | small (phase 1) | large (phase 2) |
|---|---|---|
| Tools | 18 (15 + 3 globals) | 62 (57 + 5 globals) |
| Skills | 3 | 10 |
| Server | `uvicorn mcp_server.app:app --port 8765` | `CATALOG_PROFILE=large uvicorn mcp_server.app:app --port 8766` |
| Compose service | `mcp-server` (8765) | `mcp-server-large` (8766) |
| Export | `mcp_server/tools_list.json` | `mcp_server/tools_list_large.json` |
| Mock DB | `mock_db.json` | `mock_db_large.json` (= small DB + new entities) |
| Instructions / policies | `instructions.md`, `policies.json` | `instructions_large.md`, `policies_large.json` |

Count: 3 original skills × 5 tools (15) + 7 new skills × 6 tools (42) + 5 globals = **62**.

## 1. Skills and tools

| # | Skill (id) | Tools | Deliberate overlap (confusable with) |
|---|---|---|---|
| 1 | `pedidos_logistica` (orig) | get_order_status, track_shipment, update_delivery_address, reschedule_delivery, cancel_order | – (unchanged) |
| 2 | `pagamentos_reembolsos` (orig) | get_payment_status, generate_boleto_second_copy, request_refund, get_refund_status, dispute_charge | – |
| 3 | `trocas_devolucoes` (orig) | check_return_eligibility, create_return_request, generate_return_label, create_exchange, open_warranty_claim | – |
| 4 | `assistencia_tecnica` | schedule_installation, request_technical_visit, reschedule_technical_visit, get_service_order_status, cancel_service_order, check_extended_warranty | open_warranty_claim, reschedule_delivery, cancel_order |
| 5 | `marketplace_vendedores` | get_seller_info, contact_seller, track_seller_shipment, open_seller_mediation, report_seller_issue, rate_seller | track_shipment, dispute_charge, create_return_request |
| 6 | `assinaturas` (recurring delivery) | get_subscription, pause_subscription, cancel_subscription, change_subscription_date, change_subscription_items, update_subscription_payment | cancel_order, reschedule_delivery, get_payment_status |
| 7 | `notas_fiscais_cadastro` | get_invoice, resend_invoice, request_invoice_correction, issue_return_invoice, get_purchase_receipt, update_billing_data | get_payment_status, create_return_request, update_delivery_address |
| 8 | `promocoes_precos` | validate_coupon, report_coupon_not_applied, get_promotion_terms, request_price_protection, get_gift_card_balance, redeem_gift_card | request_refund, dispute_charge |
| 9 | `fidelidade_cashback` (adjacent) | get_points_balance, get_points_statement, redeem_points, claim_missing_points, get_cashback_status, get_loyalty_tier | get_refund_status, get_gift_card_balance |
| 10 | `cartao_loja_crediario` (adjacent) | get_card_bill, generate_card_bill_copy, contest_card_transaction, request_limit_increase, block_store_card, renegotiate_debt | generate_boleto_second_copy, dispute_charge, get_payment_status |
| G | globals | get_customer_profile, search_help_center, escalate_to_human (orig) + update_contact_info, check_protocol_status | update_billing_data / update_delivery_address; get_service_order_status / get_refund_status |

Irreversible (destructive) tools: cancel_order and dispute_charge (orig), cancel_subscription,
cancel_service_order, block_store_card. No tool asks for confirmation (`confirmation=none`, as
in phase 1).

## 2. Confusable groups and where each rule lives

Each group becomes an `ambiguo` group in dev-L / test-L. Each has a disambiguation rule: a
bullet in a SKILL.md "Heurística de desambiguação" section that names every tool of the group.
`mcp_server/tests/test_mcp_tools_large.py::test_every_confusable_group_has_a_skill_rule` checks
this.

| Group | Trigger | Confusable tools | Rule (SKILL.md, bullet) |
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

## 3. Design rules

- **The originals keep their code.** The 18 original tools are the phase-1 objects.
  `mcp_server/src/mcp_server/large/overrides.py` serves *copies* of them in the large profile
  only, and each copy:
  - adds DON'T USE FOR pointers to the new siblings (`POINTERS`). The new tools point at the
    originals, so without this overlay the catalog would be one-sided;
  - fixes the two statements the large catalog makes false (`REPLACE`, `EXAMPLES`).
    escalate_to_human listed "preços, nota fiscal" as out of scope, and one of its examples was
    an invoice correction, which is now `request_invoice_correction`;
  - rebinds search_help_center to the large policy articles: the same scoring and schema, with
    10 more articles.

  Schemas, annotations and the other `_meta` keys are the originals'. A test checks that the
  overlay only *appends* pointers. The 3 original SKILL.md files are served verbatim, and the
  cross-skill rules live in the 7 new playbooks and in `instructions_large.md`.
- **New tools follow the phase-1 house style.** That means:
  - a pt-BR description with WHEN TO USE / DON'T USE FOR / PARAMETERS / CONFIRMATION / RESULT;
  - 4 `_meta` examples and keywords each;
  - `oneOf` completed | error output schemas with the shared `$defs`;
  - four honest annotations;
  - business errors as `isError` + `{code, recoverable, suggested_tool}`;
  - optional entity ids. An omitted id resolves to the customer's only entity; with several,
    the tool returns VALIDATION_ERROR + `details.options`.

  `lint_tools_list.py --strict` reports 62 tools, 0 errors and 0 warnings.
- **Mocks.** The tools are deterministic and read only the read-only `mock_db_large.json`.
  Writes never persist and return receipts derived from their arguments
  (`sha256(tool, customer, args)[:8]`). check_protocol_status recognises any receipt minted by
  this server (prefix table), plus the open protocols stored in the DB.
- **Out of scope** in the large profile: jobs, product launches and stock, password and login,
  wholesale. "Preços, promoções e cupons", "nota fiscal" and "alteração de cadastro" were out of
  scope in phase 1 and are **in scope** here. The dataset generator (T4.1) must therefore not
  reuse those phase-1 `fora_escopo` topics as out-of-scope for the large catalog.

## 4. Mock DB (`mock_db_large.json`)

`mcp_server/scripts/generate_mock_db_large.py` builds the large DB deterministically. It uses
explicit state tables and no RNG, and re-running it is byte-identical. The DB embeds the small DB
unchanged, which is asserted at import, so the same customers C001–C020 own the same orders
O0001–O0060. On top of that it adds:

- sellers and marketplace orders: 15 orders fulfilled by 6 partner sellers;
- service orders and extended warranties;
- 11 subscriptions;
- invoices: one NF-e per shipped order, plus billing profiles (4 CNPJ customers);
- coupons, promotions, current prices and gift cards;
- loyalty accounts with statements, and Pix cashback;
- 7 store cards with bills and transactions;
- open protocols.

`MOCK_DB_NOTES_LARGE.md` lists each entity's archetype and its **measured** `compatible_tools`.
The generator calls every new tool with canonical arguments on every entity, in process. The
dataset generator offers an entity for a target tool only if it is listed there. Every new tool
completes on at least 2 entities.

## 5. Review checklist (T3.1 / T3.2)

- [x] 62 tools: `tools_list_large.json` passes the lint (0 errors, 0 warnings, `--strict`).
- [x] Every G1–G12 group has a SKILL.md rule (`test_every_confusable_group_has_a_skill_rule`, 12/12).
- [x] Skill `allowed-tools` match the tools' `_meta` skill. This is checked by the host
  `fetch_catalog` (`tests/test_catalog_large.py`) and by the MCP resources test, in both profiles.
- [x] Every new tool completes on at least one mock entity (`test_every_new_tool_completes_on_some_mock_entity`).
- [x] Every new tool has at least one business-error case with code + suggested_tool asserted
  (`test_new_tool_business_error`, 63 cases).
- [x] No dead ends: every `suggested_tool` can complete. Read tools never suggest an
  irreversible action. Both profiles run the phase-1 consistency tests, with the new tools
  included in the large one.
- [x] Leakage: no new example (tool `_meta`, overlay, SKILL.md frontmatter) equals or is
  contained in a user turn of the phase-1 dev, test-v1 or test-v2 splits.
- [x] Small profile: `tools_list.json` is byte-identical and the catalog hash is `128584617807`
  (offline and in process).
