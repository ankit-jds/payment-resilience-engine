import logging
import asyncpg
from fastapi import HTTPException
from typing import Dict, Any
from app.schemas.payment import PaymentCreate
from app.core.utils import get_ist_now

logger = logging.getLogger(__name__)

async def generate_payment_intent(pool: asyncpg.Pool, payment_data: PaymentCreate) -> dict:
    """
    Generates a new PENDING payment.
    We explicitly allow unlimited tracking intents to be drawn, even if a Canonical token exists.
    A background Webhook later handles auto-refunding double-charged overlaps.
    """
    now_ist = get_ist_now()

    CREATE_PAYMENT_QUERY = """
        INSERT INTO payments (order_id, status, is_canonical, created_at)
        VALUES ($1, 'PENDING', FALSE, $2)
        RETURNING payment_id, order_id, status, is_canonical, created_at
    """

    from app.integrations.payment_provider import process_payment
    try:
        async with pool.acquire() as conn:
            # Block 1. Guarantee valid order dependencies
            order_exists = await conn.fetchval("SELECT order_id FROM orders WHERE order_id = $1", payment_data.order_id)
            if not order_exists:
                raise HTTPException(status_code=404, detail="Order UUID constraint violation: Parent Order not found in registry.")

            # Block 2. Exclusively generate blank retry intent layer
            db_row = await conn.fetchrow(CREATE_PAYMENT_QUERY, payment_data.order_id, now_ist)
            row = dict(db_row) if db_row else None
            
            # Block 3. Decoupled Network Simulation triggering the physical gateway execution
            if row:
                gateway_res = await process_payment(str(row["payment_id"]))
                
                # We strictly only update the provider_id. 
                # We deliberately leave status='PENDING' to force the Webhook Service to execute the real state-machine lock!
                if gateway_res.get("provider_payment_id"):
                    await conn.execute(
                        "UPDATE payments SET provider_payment_id = $1 WHERE payment_id = $2",
                        gateway_res["provider_payment_id"], row["payment_id"]
                    )
                    row["provider_payment_id"] = gateway_res["provider_payment_id"]
                else:
                    logger.warning(f"Simulated Network 504. External provider_payment_id entirely dropped for {row['payment_id']}")

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
