from pydantic import BaseModel, Field, field_serializer
from decimal import Decimal
import uuid
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo

class OrderCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Amount must be greater than zero")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key for the order")

class OrderResponse(BaseModel):
    order_id: uuid.UUID
    amount: Decimal
    status: str
    idempotency_key: str
    created_at: datetime
    is_existing: bool = Field(default=False, description="True if order was returned from cache due to idempotency")

    @field_serializer('created_at')
    def serialize_created_at(self, dt: datetime, _info) -> str:
        # Pydantic will intercept the raw UTC time directly and cleanly output the explicitly formatted +05:30 IST string
        return dt.astimezone(ZoneInfo('Asia/Kolkata')).isoformat()
