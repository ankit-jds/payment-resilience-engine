import asyncpg
import ssl
from app.core.config import settings

async def setup_db_pool() -> asyncpg.Pool:
    # Supabase requires SSL connection
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        ssl=ctx
    )
    if pool is None:
        raise RuntimeError("Failed to initialize database pool")
    return pool

async def teardown_db_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
