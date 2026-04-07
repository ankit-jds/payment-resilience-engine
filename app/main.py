from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.db.connection import setup_db_pool, teardown_db_pool
from app.api import orders, payments, webhooks

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await setup_db_pool()
    yield
    await teardown_db_pool(app.state.pool)

app = FastAPI(lifespan=lifespan)

app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(webhooks.router)

@app.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint that verifies database connection using the app pool.
    """
    try:
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version();")
        return {"status": "ok", "db_version": version}
    except Exception as e:
        # In a real app we'd log this, but for now we return it
        return {"status": "error", "detail": str(e)}
