from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
from decimal import Decimal

class WebhookPayload(BaseModel):
    event_type: str = Field(default="payment.updated", description="Physical routing event hook (e.g., payment.updated, refund.updated)")
    payment_id: UUID = Field(..., description="The unique UUID of the payment to update the status.")
    status: str = Field(..., description="The status of the payment.")
    amount_captured: Optional[Decimal] = Field(None, description="Explicit amount successfully mapped natively.")
