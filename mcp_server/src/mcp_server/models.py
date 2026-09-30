"""Pydantic output models. Each tool's outputSchema is `oneOf` <Completed> | ErrorResult,
discriminated by `status`, with shared `$defs` (Money, Address, OrderRef)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

ErrorCode = Literal["NOT_FOUND", "NOT_ELIGIBLE", "VALIDATION_ERROR"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(_Model):
    amount: float = Field(description="Valor com 2 casas decimais")
    currency: Literal["BRL"] = "BRL"


class Address(_Model):
    street: str
    number: str
    complement: str | None = None
    neighborhood: str
    city: str
    state: str = Field(description="UF, 2 letras")
    postal_code: str = Field(description="CEP, 8 dígitos")


class OrderRef(_Model):
    order_id: str
    status: str
    created_at: str = Field(description="Data ISO 8601")
    total: Money


class OrderItem(_Model):
    sku: str
    name: str
    quantity: int
    unit_price: Money


class ShipmentEvent(_Model):
    at: str = Field(description="Data e hora ISO 8601")
    location: str
    description: str


class Article(_Model):
    id: str
    title: str
    summary: str


class EligibilityOption(_Model):
    type: Literal["arrependimento", "devolucao_troca", "garantia"]
    eligible: bool
    deadline: str | None = Field(default=None, description="Último dia (ISO 8601)")
    tool: str = Field(description="Tool que executa esta opção")


class ErrorResult(_Model):
    status: Literal["error"] = "error"
    code: ErrorCode
    message: str
    recoverable: bool
    suggested_tool: str | None = None
    details: dict[str, Any] | None = None


class _Completed(_Model):
    status: Literal["completed"] = "completed"


class CustomerProfileResult(_Completed):
    customer_id: str
    name: str
    email_masked: str
    tier: str
    member_since: str
    default_address: Address
    orders: list[OrderRef]


class HelpCenterResult(_Completed):
    query: str
    articles: list[Article]


class EscalationResult(_Completed):
    ticket_id: str
    order_id: str | None = None
    queue: str
    response_within_hours: int


class OrderStatusResult(_Completed):
    order: OrderRef
    items: list[OrderItem]
    payment_method: str
    estimated_delivery: str | None = None
    delivered_at: str | None = None
    cancelled_at: str | None = None
    delivery_address: Address
    shipment_id: str | None = None


class ShipmentResult(_Completed):
    order_id: str
    shipment_id: str
    carrier: str
    tracking_code: str
    shipment_status: str
    eta: str | None = None
    events: list[ShipmentEvent]


class AddressUpdateResult(_Completed):
    order_id: str
    protocol: str
    previous_address: Address
    new_address: Address


class RescheduleResult(_Completed):
    order_id: str
    protocol: str
    shipment_id: str
    new_date: str
    period: str


class CancellationResult(_Completed):
    order_id: str
    protocol: str
    cancelled_at: str
    refund_amount: Money
    refund_method: str
    refund_deadline: str


class PaymentStatusResult(_Completed):
    order_id: str
    payment_id: str
    method: str
    payment_status: str
    amount: Money
    installments: int
    paid_at: str | None = None
    boleto_due_date: str | None = None


class BoletoResult(_Completed):
    order_id: str
    payment_id: str
    barcode: str
    amount: Money
    due_date: str


class RefundRequestResult(_Completed):
    order_id: str
    refund_id: str
    amount: Money
    method: str
    expected_by: str


class RefundStatusResult(_Completed):
    order_id: str
    refund_id: str
    refund_status: str
    amount: Money
    method: str
    requested_at: str | None = None
    expected_by: str


class DisputeResult(_Completed):
    order_id: str
    dispute_id: str
    payment_id: str
    amount: Money
    reason: str
    expected_resolution_by: str


class ReturnEligibilityResult(_Completed):
    order_id: str
    delivered_at: str
    eligible: bool
    options: list[EligibilityOption]


class ReturnRequestResult(_Completed):
    order_id: str
    return_id: str
    reason: str
    skus: list[str]
    refund_amount: Money
    post_by: str


class ReturnLabelResult(_Completed):
    order_id: str
    return_id: str
    label_code: str
    carrier: str
    post_by: str


class ExchangeResult(_Completed):
    order_id: str
    exchange_id: str
    sku: str
    new_variant: str
    post_by: str


class WarrantyClaimResult(_Completed):
    order_id: str
    claim_id: str
    sku: str
    warranty_until: str
    expected_response_by: str


def output_schema(completed: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema `oneOf` [completed, error] discriminated by `status`.

    Every schema carries the shared `$defs` (Money, Address, OrderRef) so hosts see one shape.
    """
    union = Annotated[completed | ErrorResult, Field(discriminator="status")]
    schema = TypeAdapter(union).json_schema(ref_template="#/$defs/{model}")
    shared = {}
    for model in (Money, Address, OrderRef):
        shared[model.__name__] = model.model_json_schema(ref_template="#/$defs/{model}")
        shared[model.__name__].pop("$defs", None)  # nested refs resolve against the root $defs
    schema["$defs"] = {**shared, **schema["$defs"]}
    return {"type": "object", **schema}
