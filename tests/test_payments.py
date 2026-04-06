import uuid
import pytest
import asyncpg
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

def generate_db_mock_payment(payment_uuid, order_uuid, status="PENDING", is_canonical=False):
    """Helper generator to construct a static mocked asyncpg row payload mimicking genuine PostgreSQL results"""
    return {
        "payment_id": payment_uuid,
        "order_id": order_uuid,
        "status": status,
        "is_canonical": is_canonical,
        "created_at": datetime.utcnow()
    }

# ===============================================
# CRITICAL BEST PRACTICES: GLOBAL FIXTURE
# ===============================================

@pytest.fixture(autouse=True)
def mock_db_connection():
    """
    Forcefully intercept the FastAPI Lifespan database pool startup. 
    Without this, TestClient still establishes a literal TCP network connection to Supabase during router startup
    even if the individual `.fetchrow` queries are later mocked. This creates absolute offline isolation.
    """
    with patch("app.db.connection.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        # pool must be a MagicMock natively because pool.acquire() is actual an active synchronous function!
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()  # IMPORTANT: Allows FastAPI lifespan teardown via `await pool.close()`
        
        mock_acquire_context = AsyncMock()
        mock_conn = AsyncMock()
        
        # 1. pool.acquire() returns a context object
        mock_pool.acquire.return_value = mock_acquire_context
        # 2. `async with` triggers __aenter__, yielding the isolated socket mock
        mock_acquire_context.__aenter__.return_value = mock_conn
        
        mock_create_pool.return_value = mock_pool
        
        yield mock_conn

# ===============================================
# SUCCESS CASES (201)
# ===============================================

def test_create_payment_intent_success(mock_db_connection):
    """Test standard payment creation strictly mocks database interaction yielding 201 effectively severing live DB ties."""
    shared_order_uuid = uuid.uuid4()
    payment_uuid = uuid.uuid4()
    
    # Mock `fetchval` (checking if order exists) to natively return the order_id affirmatively
    mock_db_connection.fetchval.return_value = shared_order_uuid
    
    # Mock `fetchrow` to return the new completely isolated payment payload
    mock_db_connection.fetchrow.return_value = generate_db_mock_payment(payment_uuid, shared_order_uuid)
    
    with TestClient(app) as client:
        # Action 1: Create Payment Intent mapping back to valid Order
        response = client.post("/payments/", json={"order_id": str(shared_order_uuid)})
        assert response.status_code == 201
        
        data = response.json()
        assert data["payment_id"] == str(payment_uuid)
        assert data["order_id"] == str(shared_order_uuid)
        assert data["status"] == "PENDING"
        assert data["is_canonical"] is False

# ===============================================
# FAILURE & EDGE CASES (404 / 422 / 500)
# ===============================================

def test_create_payment_invalid_uuid_fails_validation():
    """Test Pydantic cleanly rejects garbage UUID strings returning HTTP 422 before targeting DB."""
    with TestClient(app) as client:
        # Action 1: Invalid UUID formatting natively rejected by schemas
        response = client.post("/payments/", json={"order_id": "not-a-valid-uuid-12345"})
        assert response.status_code == 422
        assert "input should be a valid uuid" in response.json()["detail"][0]["msg"].lower()

def test_create_payment_parent_order_not_found(mock_db_connection):
    """Test that if the database fetchval returns None for the parent order lookup, we cleanly block creating an orphaned payment!"""
    shared_order_uuid = uuid.uuid4()
    
    # Mock `fetchval` to return None, natively simulating the Parent Order UUID constraint failure.
    mock_db_connection.fetchval.return_value = None
    
    with TestClient(app) as client:
        # Action 1: Create Payment triggering explicit 404 Parent logic
        response = client.post("/payments/", json={"order_id": str(shared_order_uuid)})
        assert response.status_code == 404
        assert "Order UUID constraint violation" in response.json()["detail"]

def test_db_postgres_rejection_yields_500(mock_db_connection):
    """Test strict HTTP 500 mapping when Postgres throws a physical database-layer error."""
    shared_order_uuid = uuid.uuid4()
    
    # Allow `fetchval` to successfully return the parent order existence
    mock_db_connection.fetchval.return_value = shared_order_uuid
    mock_db_connection.fetchrow.side_effect = asyncpg.exceptions.DataError("Mocked Postgres Error")
    
    with TestClient(app) as client:
        # Action 1: Create triggering Postgres engine constraint rejection
        response = client.post("/payments/", json={"order_id": str(shared_order_uuid)})
        assert response.status_code == 500
        assert "rejected the payment insertion" in response.json()["detail"]

def test_db_unexpected_system_error_yields_500(mock_db_connection):
    """Test totally unpredictable catastrophic system errors bubble to 500 cleanly."""
    shared_order_uuid = uuid.uuid4()
    
    mock_db_connection.fetchval.return_value = shared_order_uuid
    mock_db_connection.fetchrow.side_effect = Exception("Wildcard Memory Blowout")
    
    with TestClient(app) as client:
        # Action 1: Create triggering catastrophic Python hardware limit panic
        response = client.post("/payments/", json={"order_id": str(shared_order_uuid)})
        assert response.status_code == 500
        assert "collapsed the system" in response.json()["detail"]

def test_db_returns_no_row_data_yields_500(mock_db_connection):
    """Test failsafe where database successfully executed but bizarrely returned completely empty payload."""
    shared_order_uuid = uuid.uuid4()
    
    mock_db_connection.fetchval.return_value = shared_order_uuid
    mock_db_connection.fetchrow.return_value = None
    
    with TestClient(app) as client:
        # Action 1: Create triggering silent Postgres return logic corruption
        response = client.post("/payments/", json={"order_id": str(shared_order_uuid)})
        assert response.status_code == 500
        assert "no response payload" in response.json()["detail"]
