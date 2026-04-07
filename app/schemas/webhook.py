from pydantic import BaseModel, Field
from uuid import UUID

class WebhookPayload(BaseModel):
    payment_id: UUID = Field(..., description="The unique UUID of the payment to update the status.")
    status: str = Field(..., description="The status of the payment.")
