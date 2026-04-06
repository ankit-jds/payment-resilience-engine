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
    try:
        async with pool.acquire() as conn:
            CREATE_ORDER_QUERY = """
                INSERT INTO orders (idempotency_key, request_hash, amount)
                VALUES ($1, $2, $3)
                ON CONFLICT (idempotency_key) 
                DO UPDATE SET idempotency_key = orders.idempotency_key
                RETURNING order_id, amount, status, idempotency_key, (xmax = 0) AS inserted;
            """
            row = await conn.fetchrow(CREATE_ORDER_QUERY, final_idempotency_key, request_hash, order_data.amount)
            
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
        "is_existing": not row["inserted"]
    }
