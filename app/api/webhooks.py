from fastapi import APIRouter, Request, status
from app.schemas.webhook import WebhookPayload
from app.services.webhook_service import process_webhook_payload

router = APIRouter(prefix="/webhook", tags=["webhooks"])

@router.post("/", status_code=status.HTTP_200_OK)
async def handle_webhook(
    request: Request,
    payload: WebhookPayload
):
    pool = request.app.state.pool
    
    result = await process_webhook_payload(pool, payload)
    return result
