"""Output models of the 44 large-profile tools. Same contract as `mcp_server.models`: each
tool's outputSchema is `oneOf` <Completed> | ErrorResult, discriminated by `status`, with the
shared `$defs` (Money, Address, OrderRef)."""

from __future__ import annotations

from pydantic import Field

from mcp_server.models import Money, ShipmentEvent, _Completed, _Model

# ---------------------------------------------------------------- assistencia_tecnica


class ServiceOrderResult(_Completed):
    service_order_id: str
    order_id: str
    sku: str
    type: str = Field(description="instalacao | visita_tecnica")
    service_status: str = Field(description="agendada | em_atendimento | concluida | cancelada")
    scheduled_for: str
    period: str
    technician: str | None = None


class ServiceOrderCancelResult(_Completed):
    service_order_id: str
    protocol: str
    cancelled_at: str


class ExtendedWarrantyResult(_Completed):
    order_id: str
    sku: str
    legal_warranty_until: str
    has_extended_warranty: bool
    extended_warranty_id: str | None = None
    plan_months: int | None = None
    extended_status: str | None = None
    valid_until: str | None = None
    coverage: str | None = None


# ---------------------------------------------------------------- marketplace_vendedores


class SellerInfoResult(_Completed):
    order_id: str
    seller_id: str
    seller_name: str
    cnpj_masked: str
    rating: float
    ratings_count: int
    response_hours: int
    seller_status: str


class SellerContactResult(_Completed):
    order_id: str
    seller_id: str
    protocol: str
    respond_by: str


class SellerShipmentResult(_Completed):
    order_id: str
    seller_id: str
    carrier: str
    tracking_code: str | None = None
    shipment_status: str
    eta: str | None = None
    events: list[ShipmentEvent]


class SellerMediationResult(_Completed):
    order_id: str
    seller_id: str
    mediation_id: str
    reason: str
    expected_resolution_by: str


class SellerReportResult(_Completed):
    seller_id: str
    report_id: str
    issue_type: str


class SellerRatingResult(_Completed):
    order_id: str
    seller_id: str
    rating: int
    protocol: str


# ---------------------------------------------------------------- assinaturas


class SubscriptionItem(_Model):
    sku: str
    name: str
    quantity: int
    unit_price: Money


class SubscriptionResult(_Completed):
    subscription_id: str
    plan_name: str
    subscription_status: str = Field(description="active | paused | cancelled")
    items: list[SubscriptionItem]
    frequency_days: int
    next_delivery: str | None = None
    paused_until: str | None = None
    payment_method: str
    card_last4: str | None = None
    price_per_delivery: Money


class SubscriptionChangeResult(_Completed):
    subscription_id: str
    protocol: str
    subscription_status: str
    next_delivery: str | None = None
    paused_until: str | None = None
    items: list[SubscriptionItem] | None = None
    payment_method: str | None = None
    card_last4: str | None = None
    price_per_delivery: Money | None = None


# ---------------------------------------------------------------- notas_fiscais_cadastro


class InvoiceResult(_Completed):
    order_id: str
    invoice_number: str
    series: str
    issued_at: str
    access_key: str = Field(description="Chave de acesso da NF-e, 44 dígitos")
    amount: Money
    billing_name: str
    doc_masked: str


class InvoiceResendResult(_Completed):
    order_id: str
    invoice_number: str
    protocol: str
    channel: str
    destination_masked: str


class InvoiceCorrectionResult(_Completed):
    order_id: str
    invoice_number: str
    protocol: str
    field: str
    expected_by: str


class ReturnInvoiceResult(_Completed):
    order_id: str
    return_invoice_number: str
    reference_invoice: str
    sku: str
    amount: Money
    post_by: str


class PurchaseReceiptResult(_Completed):
    order_id: str
    receipt_code: str
    paid_at: str
    method: str
    installments: int
    amount: Money
    payment_status: str


class BillingUpdateResult(_Completed):
    customer_id: str
    protocol: str
    field: str
    new_value: str
    effective_from: str


# ---------------------------------------------------------------- promocoes_precos


class CouponResult(_Completed):
    code: str
    valid: bool
    kind: str
    value: float
    min_order: Money
    category: str | None = None
    valid_until: str
    first_purchase_only: bool
    reasons: list[str] = Field(description="Por que o cupom não vale hoje, se não vale")


class CouponClaimResult(_Completed):
    order_id: str
    code: str
    protocol: str
    expected_credit: Money
    expected_by: str


class PromotionTermsResult(_Completed):
    promotion_id: str
    name: str
    valid_from: str
    valid_until: str
    active: bool
    coupons: list[str]
    terms: str


class PriceProtectionResult(_Completed):
    order_id: str
    sku: str
    paid_price: Money
    current_price: Money
    credit: Money
    gift_card_code: str
    expires_at: str


class GiftCard(_Model):
    code: str
    card_status: str
    balance: Money
    expires_at: str


class GiftCardBalanceResult(_Completed):
    gift_cards: list[GiftCard]
    total_balance: Money


class GiftCardRedeemResult(_Completed):
    code: str
    protocol: str
    credited: Money
    expires_at: str


# ---------------------------------------------------------------- fidelidade_cashback


class PointsBalanceResult(_Completed):
    customer_id: str
    points: int
    pending_points: int
    expiring_points: int
    expiring_at: str
    tier: str


class PointsEntry(_Model):
    date: str
    description: str
    points: int
    order_id: str | None = None


class PointsStatementResult(_Completed):
    customer_id: str
    since: str
    entries: list[PointsEntry]
    balance: int


class PointsRedeemResult(_Completed):
    protocol: str
    points: int
    reward: str
    voucher_code: str
    value: Money
    remaining_points: int


class MissingPointsResult(_Completed):
    order_id: str
    protocol: str
    expected_points: int
    expected_by: str


class CashbackResult(_Completed):
    order_id: str
    promotion_id: str
    amount: Money
    cashback_status: str = Field(
        description="aguardando_entrega | pendente | disponivel | cancelado"
    )
    release_at: str | None = None


class LoyaltyTierResult(_Completed):
    customer_id: str
    tier: str
    lifetime_points: int
    next_tier: str | None = None
    points_to_next_tier: int
    benefits: list[str]


# ---------------------------------------------------------------- cartao_loja_crediario


class CardTransaction(_Model):
    id: str
    date: str
    description: str
    amount: Money
    contested: bool


class CardBillResult(_Completed):
    card_last4: str
    card_status: str
    bill_status: str = Field(description="open | closed | overdue | paid")
    due_date: str
    amount: Money
    minimum_payment: Money
    amount_due: Money
    limit: Money
    available: Money
    transactions: list[CardTransaction]


class CardBillCopyResult(_Completed):
    card_last4: str
    barcode: str
    amount: Money
    due_date: str


class CardContestResult(_Completed):
    transaction_id: str
    contest_id: str
    amount: Money
    reason: str
    expected_resolution_by: str


class LimitIncreaseResult(_Completed):
    card_last4: str
    protocol: str
    previous_limit: Money
    approved_limit: Money
    requested_limit: Money


class CardBlockResult(_Completed):
    card_last4: str
    protocol: str
    reason: str
    blocked_at: str
    replacement_by: str


class DebtRenegotiationResult(_Completed):
    agreement_id: str
    debt_amount: Money
    installments: int
    installment_amount: Money
    first_due_date: str


# ---------------------------------------------------------------- globals


class ContactUpdateResult(_Completed):
    customer_id: str
    protocol: str
    email_masked: str | None = None
    phone_masked: str | None = None


class ProtocolStatusResult(_Completed):
    protocol: str
    kind: str
    subject: str
    protocol_status: str
    opened_at: str | None = None
    expected_by: str | None = None
