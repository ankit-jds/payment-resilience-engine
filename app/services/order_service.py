import hashlib
import json
import asyncpg
import logging
from fastapi import HTTPException
from app.schemas.order import OrderCreate
from typing import Dict, Any


async def create_order_idempotent(pool: asyncpg.Pool, order_data: OrderCreate) -> Dict[str, Any]:
    # 1. Hybrid Request Hashing
    request_hash = "HASH_GENERATION_FAILED"
    try:
        # Convert Decimal strictly to string to ensure deterministic serialization
        payload_str = json.dumps({"amount": str(order_data.amount)}, sort_keys=True)
        request_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    except Exception as hash_err:
        logging.error(f"Request hashing failed: {hash_err}")
        # If hash fails AND client supplied no idempotency key, we are completely unsafe.
        if not order_data.idempotency_key:
            raise HTTPException(
                status_code=500, 
                detail="Idempotency key generation failed and no client fallback key was provided."
            )
            
    # 2. Key Resolution Strategy
    # Give priority to explicitly passed client keys. Fallback to our generated hash.
    final_idempotency_key = order_data.idempotency_key if order_data.idempotency_key else request_hash

    # 3. DB interactions with robust exception handling
    from app.core.utils import get_ist_now
    
    from app.integrations.payment_provider import create_order
    try:
        async with pool.acquire() as conn:
            CREATE_ORDER_QUERY = """
                INSERT INTO orders (idempotency_key, request_hash, amount, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (idempotency_key) 
                DO UPDATE SET idempotency_key = orders.idempotency_key
                RETURNING order_id, amount, status, idempotency_key, provider_order_id, created_at, (xmax = 0) AS inserted;
            """
            now_ist = get_ist_now()

            # Pass our IST localized time directly into Postgres as parameter 4
            db_row = await conn.fetchrow(CREATE_ORDER_QUERY, final_idempotency_key, request_hash, order_data.amount, now_ist)
            
            # Unpack dynamically enabling in-memory modification parsing
            row = dict(db_row) if db_row else None
            
            # 3B. External Gateway Registration safely completely decoupled natively
            if row and row["inserted"]:
                gateway_res = await create_order(str(row["order_id"]))
                
                if gateway_res["status"] == "SUCCESS":
                    await conn.execute("UPDATE orders SET provider_order_id = $1 WHERE order_id = $2", gateway_res["provider_order_id"], row["order_id"])
                    row["provider_order_id"] = gateway_res["provider_order_id"]
                else:
                    logging.warning(f"Simulated Network 504. External provider_order_id entirely dropped for {row['order_id']}")

    except asyncpg.exceptions.PostgresError as db_error:
        logging.error(f"Database insertion error: {db_error}")
        raise HTTPException(
            status_code=500, 
            detail="The database rejected the order insertion transaction."
        )
    except Exception as unk_err:
        logging.error(f"Unexpected system error: {unk_err}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error collapsed the system while saving the order."
        )

    # 4. Result validation
    if not row:
        raise HTTPException(status_code=500, detail="Database returned no response payload after upsert.")

    return {
        "order_id": row["order_id"],
        "amount": row["amount"],
        "status": row["status"],
        "idempotency_key": row["idempotency_key"],
        "provider_order_id": row.get("provider_order_id"),
        "created_at": row["created_at"],
        "is_existing": not row["inserted"]
    }
