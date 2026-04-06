from pydantic import BaseModel, Field
from decimal import Decimal
import uuid
from typing import Optional

class OrderCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Amount must be greater than zero")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key for the order")

class OrderResponse(BaseModel):
    order_id: uuid.UUID
    amount: Decimal
    status: str
    idempotency_key: str
    is_existing: bool = Field(default=False, description="True if order was returned from cache due to idempotency")
