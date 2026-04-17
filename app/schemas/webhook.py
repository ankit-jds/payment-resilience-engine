from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional


class WebhookPayload(BaseModel):
    event_type: str = Field(default="payment.updated", description="Physical routing event hook (e.g., payment.updated, refund.updated)")
    payment_id: UUID = Field(..., description="The unique UUID of the payment to update the status.")
    status: str = Field(..., description="The status of the payment.")
    amount_captured: Optional[int] = Field(None, description="Explicit amount securely locked mapping paise/cents natively.")
