import asyncio
import logging
import asyncpg
from typing import List, Dict

# Assuming proper path contexts if explicitly operated directly from /app securely.
from app.core.config import settings
from app.integrations.payment_provider import process_refund

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RefundWorker")

async def claim_batch(pool: asyncpg.Pool, batch_size: int = 50) -> List[Dict]:
    """
    CRITICAL ARCHITECTURE: Hit-and-Run Polling.
    We physically lock rows explicitly using SKIP LOCKED, instantly transition their status 
    to 'PROCESSING', and then immediately drop the PostgreSQL connection!
    This absolutely guarantees we NEVER hold database locks across HTTP network calls.
    """
    claimed = []
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # The ultimate Postgres Queue Pattern securely preventing horizontal-scale clashes!
                CLAIM_QUERY = """
                    UPDATE refunds
                    SET status = 'PROCESSING'
                    WHERE refund_id IN (
                        SELECT refund_id 
                        FROM refunds 
                        WHERE status = 'PENDING_CONFIRMATION' 
                        LIMIT $1 
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING refund_id, payment_id;
                """
                records = await conn.fetch(CLAIM_QUERY, batch_size)
                
                # Unpack asyncpg Native records out of memory blocks quickly
                claimed = [dict(record) for record in records]
                
    except Exception as e:
        logger.error(f"Database execution failed while claiming batches: {e}")
        
    return claimed


async def process_and_finalize(pool: asyncpg.Pool, claimed_records: List[Dict]):
    """
    Executes entirely entirely free of any Postgres locks securely over the Network layer!
    """
    for record in claimed_records:
        refund_id = record["refund_id"]
        payment_id = record["payment_id"]
        
        try:
            # 1. Physical simulated network flight natively isolated from Database!
            gateway_res = await process_refund(str(payment_id))
            
            # 2. Acquire a micro-lock strictly for the tiny update mapping!
            async with pool.acquire() as conn:
                if gateway_res["status"] in ["SUCCESS", "FAILED"]:
                    await conn.execute("""
                        UPDATE refunds 
                        SET status = $1, provider_refund_id = $2
                        WHERE refund_id = $3
                    """, gateway_res["status"], gateway_res["provider_refund_id"], refund_id)
                    logger.info(f"[SUCCESS] Refund {refund_id} permanently structurally transitioned to {gateway_res['status']}")
                
                elif gateway_res["status"] == "TIMEOUT":
                    # If Stripe physically drops network, downgrade safely back to the queue loop!
                    await conn.execute("""
                        UPDATE refunds 
                        SET status = 'PENDING_CONFIRMATION' 
                        WHERE refund_id = $1
                    """, refund_id)
                    logger.warning(f"[NETWORK 504] Refund {refund_id} hit TIMEOUT lockup. Successfully rolled back to queue natively.")
        
        except Exception as err:
            logger.error(f"[SYSTEM FAILURE] Refund execution {refund_id} critically crashed gracefully natively: {err}")


async def process_pending_refunds_loop(pool: asyncpg.Pool):
    """Orchestrates exactly the polling decoupling definitively."""
    records = await claim_batch(pool)
    if not records:
        return
        
    logger.info(f"Worker securely claimed {len(records)} pending refunds natively. Processing...")
    await process_and_finalize(pool, records)


async def start_worker():
    """Main execution engine loop securely polling interval bounds seamlessly."""
    logger.info("Initializing Refund Worker Architecture Engine natively...")
    pool = await asyncpg.create_pool(settings.database_url)
    try:
        while True:
            await process_pending_refunds_loop(pool)
            await asyncio.sleep(3)  # Interval poll
    except asyncio.CancelledError:
        logger.info("Refund Worker explicitly securely shutting down...")
    finally:
        await pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(start_worker())
    except KeyboardInterrupt:
        logger.info("Manual Kill-Switch invoked completely terminating native engine...")
