import logging
import asyncpg
from fastapi import HTTPException
from app.schemas.webhook import WebhookPayload
from app.core.utils import get_ist_now

logger = logging.getLogger(__name__)

async def process_webhook_payload(pool: asyncpg.Pool, payload: WebhookPayload) -> dict:
    """
    Applies the Payment Webhook State Machine natively guaranteeing total system convergence cleanly.
    Strictly isolated mapping handles complex Double-Success overlapping constraints accurately.
    """
    valid_statuses = {"SUCCESS", "FAILED"}
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid webhook status natively rejected. Allowed: {valid_statuses}")

    try:
        async with pool.acquire() as conn:
            # We strictly enforce PostgreSQL row-level locks eliminating double-click execution errors dynamically
            async with conn.transaction():
                # 1. Lock the Payment row specifically cleanly forcing parallel overlapping hooks to execute sequentially!
                payment_row = await conn.fetchrow("""
                    SELECT status, order_id 
                    FROM payments 
                    WHERE payment_id = $1 FOR UPDATE
                """, payload.payment_id)

                if not payment_row:
                    raise HTTPException(status_code=404, detail="Webhook payload natively rejected. Unknown payment mapping.")

                current_status = payment_row["status"]
                order_id = payment_row["order_id"]

                # ===============================================================
                # STATE MACHINE BRANCH A: FAILURE PROCESSING
                # ===============================================================
                if payload.status == "FAILED":
                    # Constraint Layer 1: No State Regression. Once a pipeline hits SUCCESS mapping, FAIL hooks safely die!
                    if current_status in ("SUCCESS", "DUPLICATE_SUCCESS", "FAILED"):
                        return {"message": f"Webhook rigorously skipped natively. Payment firmly isolated mapping terminal logic: {current_status}"}

                    await conn.execute("UPDATE payments SET status = 'FAILED' WHERE payment_id = $1", payload.payment_id)
                    return {"message": "Payment dynamically locked into FAILED state perfectly! Order state was explicitly preserved and not modified by this hook."}

                # ===============================================================
                # STATE MACHINE BRANCH B: SUCCESS PROCESSING
                # ===============================================================
                elif payload.status == "SUCCESS":
                    if current_status in ("SUCCESS", "DUPLICATE_SUCCESS"):
                        return {"message": "Webhook securely skipped logically. Duplicate SUCCESS identical payload natively captured and dropped."}

                    # Canonical Separation Logic
                    # Attempt updating the parent Order exclusively securely isolating exactly the FIRST physical execution arrival
                    updated_order = await conn.fetchrow("""
                        UPDATE orders 
                        SET status = 'PAID' 
                        WHERE order_id = $1 AND status != 'PAID' 
                        RETURNING order_id
                    """, order_id)

                    if updated_order:
                        # Success Scenario 1: Flawless Canonical execution! Payment definitively won the pipeline securely.
                        await conn.execute("""
                            UPDATE payments 
                            SET status = 'SUCCESS', is_canonical = TRUE 
                            WHERE payment_id = $1
                        """, payload.payment_id)
                        return {"message": "Flawless canonical execution seamlessly triggered! Order efficiently flagged PAID correctly avoiding duplicate loops."}
                    else:
                        # Success Scenario 2: Order explicitly evaluated as ALREADY PAID historically!
                        # This mathematically proves a separate disjoint layer previously won uniquely natively!
                        await conn.execute("""
                            UPDATE payments 
                            SET status = 'DUPLICATE_SUCCESS', is_canonical = FALSE 
                            WHERE payment_id = $1
                        """, payload.payment_id)

                        # Instantly strictly flag explicitly queued mapping refund intents gracefully!
                        # This exact command handles robust DB constraints trapping overlapping triggers avoiding memory leaks identically.
                        now_ist = get_ist_now()
                        await conn.execute("""
                            INSERT INTO refunds (payment_id, status, created_at)
                            VALUES ($1, 'PENDING_CONFIRMATION', $2)
                            ON CONFLICT (payment_id) DO NOTHING
                        """, payload.payment_id, now_ist)

                        return {"message": "Duplicate success rigorously isolated correctly natively! Payment effectively locked into DUPLICATE_SUCCESS safely firing offline refund intent mapping."}

    except HTTPException as http_exc:
        logger.warning(f"Webhook precisely halted logical schema validation requirements natively: {http_exc.detail}")
        raise
    except asyncpg.exceptions.PostgresError as db_error:
        logger.error(f"Database constraint execution rigorously blocked native layers natively: {db_error}")
        raise HTTPException(status_code=500, detail="Database internally rejected exact webhook schema constraints gracefully.")
    except Exception as unk_err:
        logger.error(f"Unexpected system crash gracefully logged wrapping internal structural collapse dynamically: {unk_err}")
        raise HTTPException(status_code=500, detail="Internal system mapping safely handled logical crash directly preserving separation.")
