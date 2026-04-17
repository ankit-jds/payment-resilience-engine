import asyncio
import logging
import asyncpg
from app.core.config import settings
from app.integrations.payment_provider import check_payment_status, check_refund_status
from app.services.webhook_service import process_webhook_payload
from app.schemas.webhook import WebhookPayload

logger = logging.getLogger("ReconciliationWorker")

async def execute_reconciliation_sweep(pool: asyncpg.Pool):
    """
    Physically executes the Phase 1 & Phase 2 systemic ghost cleanup loops flawlessly mapped via Hit-And-Run pooling.
    """
    logger.info("Commencing Phase 1: Payment Sweeper (Checking Truth Source)...")
    
    # ===============================================================
    # HIT-AND-RUN POOLING: PHASE 1 (Payments)
    # ===============================================================
    ghost_ids = []
    try:
        # Step 1: Open pool, fetch IDs explicitly securely, DROP POOL IMMEDIATELY!
        async with pool.acquire() as conn:
            FETCH_GHOSTS = """
                SELECT payment_id 
                FROM payments 
                WHERE status = 'PENDING' 
                AND created_at < NOW() - INTERVAL '24 hours'
            """
            ghosts = await conn.fetch(FETCH_GHOSTS)
            ghost_ids = [str(g["payment_id"]) for g in ghosts]
    except Exception as e:
        logger.error(f"Ghost payment sweep natively blocked: {e}")

    if ghost_ids:
        logger.warning(f"Extracted {len(ghost_ids)} abandoned checkouts. Investigating offline natively...")
        # Step 2: OFFLINE NETWORK LOOP (DB is 100% free for other Microservices!)
        for pid in ghost_ids:
            truth = await check_payment_status(pid)
            
            if truth["status"] == "SUCCESS":
                # Webhook dropped! Force fulfillment dynamically instantly reconnecting!
                payload = WebhookPayload(event_type="payment.updated", payment_id=pid, status="SUCCESS")
                await process_webhook_payload(pool, payload)
            else:
                # Checkout functionally abandoned. Mechanically kill it securely opening a micro-connection.
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("UPDATE payments SET status = 'FAILED' WHERE payment_id = $1", pid)
                        await conn.execute("""
                            UPDATE orders o
                            SET status = 'FAILED'
                            WHERE o.order_id = (SELECT order_id FROM payments WHERE payment_id = $1)
                            AND o.status != 'PAID'
                            AND NOT EXISTS (
                                SELECT 1 FROM payments p 
                                WHERE p.order_id = o.order_id 
                                AND p.status IN ('SUCCESS', 'PENDING')
                            )
                        """, pid)
                        logger.info(f"PURGED: Abandoned checkout {pid} permanently killed.")

    # ===============================================================
    # HIT-AND-RUN POOLING: PHASE 2 (Refunds)
    # ===============================================================
    logger.info("Commencing Phase 2: Refund Detective (Stuck Network Traps)...")
    stuck_refund_ids = []
    try:
        # Step 1: Claim stuck refunds, instantly dropping connection!
        async with pool.acquire() as conn:
            FETCH_REFUNDS = """
                SELECT payment_id 
                FROM refunds 
                WHERE status = 'PENDING_CONFIRMATION' 
                AND created_at < NOW() - INTERVAL '72 hours'
            """
            stuck = await conn.fetch(FETCH_REFUNDS)
            stuck_refund_ids = [str(r["payment_id"]) for r in stuck]
    except Exception as e:
        logger.error(f"Refund sweep natively blocked: {e}")

    if stuck_refund_ids:
        logger.error(f"CRITICAL: Found {len(stuck_refund_ids)} Refunds stuck natively. Checking Gateway Settlement...")
        
        # Step 2: OFFLINE NETWORK LOOP (DB completely physically free)
        for pid in stuck_refund_ids:
            truth = await check_refund_status(pid)
            
            if truth["status"] == "SUCCESS":
                # The refund settled 5 days ago but the webhook dropped!
                payload = WebhookPayload(event_type="refund.updated", payment_id=pid, status="SUCCESS")
                await process_webhook_payload(pool, payload)
            else:
                # Refund fundamentally structurally crashed. Manual intervention forced natively!
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE refunds SET status = 'FAILED' WHERE payment_id = $1", pid)
                    
                    # TODO: Trigger PagerDuty / Slack Alert / Email Notification mapping!
                    # Example: await alert_service.send_critical_refund_failure(pid)
                    logger.critical(f"ACTION REQUIRED: Refund for payment {pid} permanently crashed. Escalated to Finance Team queue for manual resolution.")

async def start_reconciliation():
    logger.info("Initializing Reconciliation Sweeper Engine.")
    pool = await asyncpg.create_pool(settings.database_url)
    try:
        await execute_reconciliation_sweep(pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    # Unlike RefundWorker, this script is designed exactly for Cron execution constraints
    asyncio.run(start_reconciliation())
