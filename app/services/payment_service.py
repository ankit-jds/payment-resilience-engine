import logging
import asyncpg
from fastapi import HTTPException
from typing import Dict, Any
from app.schemas.payment import PaymentCreate
from app.core.utils import get_ist_now
import asyncio
from app.integrations.payment_provider import process_payment
from app.services.webhook_service import process_webhook_payload
from app.schemas.webhook import WebhookPayload

logger = logging.getLogger(__name__)

async def _bg_simulate_frontend_and_webhook(pool: asyncpg.Pool, payment_id: str):
    """
    Offline simulator exactly mapping the React Client SDK latency combined with the 
    subsequent Gateway Webhook generation. Operates entirely independently of the API payload lock natively.
    """
    try:
        # 1. Simulate the React App pinging SDK directly entirely physically decoupled
        gateway_res = await process_payment(payment_id)
        
        # 2. Add the tracking metadata natively decoupled
        if gateway_res.get("provider_payment_id"):
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE payments SET provider_payment_id = $1 WHERE payment_id = $2",
                    gateway_res["provider_payment_id"], payment_id
                )
                
        # 3. Gateway physically fires the Webhook Payload asynchronously cleanly
        test_payload = WebhookPayload(payment_id=payment_id, status=gateway_res["status"])
        await process_webhook_payload(pool, test_payload)
        
    except Exception as e:
        logger.error(f"Background Gateway Simulation mechanically crashed natively: {e}")


async def generate_payment_intent(pool: asyncpg.Pool, payment_data: PaymentCreate) -> dict:
    """
    Generates a new PENDING payment natively.
    Returns the PENDING intent ID completely decoupled instantly off the HTTP socket natively.
    """
    now_ist = get_ist_now()

    CREATE_PAYMENT_QUERY = """
        INSERT INTO payments (order_id, status, is_canonical, created_at)
        VALUES ($1, 'PENDING', FALSE, $2)
        RETURNING payment_id, order_id, status, is_canonical, created_at
    """

    try:
        async with pool.acquire() as conn:
            # Block 1. Guarantee valid order dependencies
            order_exists = await conn.fetchval("SELECT order_id FROM orders WHERE order_id = $1", payment_data.order_id)
            if not order_exists:
                raise HTTPException(status_code=404, detail="Order UUID constraint violation: Parent Order not found in registry.")

            # Block 2. Exclusively generate blank retry intent layer
            db_row = await conn.fetchrow(CREATE_PAYMENT_QUERY, payment_data.order_id, now_ist)
            row = dict(db_row) if db_row else None
            
            # Block 3. Instantly Drop execution loop safely completely decoupled from HTTP Wait lock!
            if row:
                asyncio.create_task(_bg_simulate_frontend_and_webhook(pool, str(row["payment_id"])))

    except HTTPException as http_exc:
        logger.warning(f"Payment generation explicitly halted constraints: {http_exc.detail}")
        raise
    except asyncpg.exceptions.PostgresError as db_error:
        logger.error(f"Database insertion error: {db_error}")
        raise HTTPException(
            status_code=500, 
            detail="The database rejected the payment insertion transaction."
        )
    except Exception as unk_err:
        logger.error(f"Unexpected system error: {unk_err}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error collapsed the system while saving the payment."
        )

    # 4. Result validation
    if not row:
        raise HTTPException(status_code=500, detail="Database returned no response payload after insert.")

    return {
        "payment_id": str(row["payment_id"]),
        "order_id": str(row["order_id"]),
        "provider_payment_id": row.get("provider_payment_id"),
        "status": row["status"],
        "is_canonical": row["is_canonical"],
        "created_at": row["created_at"]
    }
