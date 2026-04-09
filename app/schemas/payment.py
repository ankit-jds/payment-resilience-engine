from pydantic import BaseModel, ConfigDict, Field, field_serializer
from uuid import UUID
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

class PaymentCreate(BaseModel):
    order_id: UUID = Field(..., description="The unique UUID of the Order to attach the payment sequence.")

class PaymentResponse(BaseModel):
    payment_id: UUID
    order_id: UUID
    status: str
    provider_payment_id: Optional[str] = None
    is_canonical: bool
    created_at: datetime

    @field_serializer('created_at')
    def serialize_created_at(self, dt: datetime, _info) -> str:
        return dt.astimezone(ZoneInfo('Asia/Kolkata')).isoformat()
