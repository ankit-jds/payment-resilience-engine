import uuid
import pytest
import asyncpg
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

def generate_db_mock(order_uuid, amount, key, inserted):
    """Helper generator to construct a static mocked asyncpg row payload mimicking genuine PostgreSQL results"""
    return {
        "order_id": order_uuid,
        "amount": Decimal(str(amount)),
        "status": "CREATED",
        "idempotency_key": key,
        "created_at": datetime.utcnow(),
        "inserted": inserted
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
# SUCCESS CASES (200 / 201)
# ===============================================

def test_create_order_no_idempotency_key_provided(mock_db_connection):
    """Test standard order creation strictly mocks database interaction yielding 201/200 effectively severing live DB ties."""
    shared_uuid = uuid.uuid4()
    
    mock_db_connection.fetchrow.side_effect = [
        generate_db_mock(shared_uuid, 14.55, "hash-fallback-key", True),  
        generate_db_mock(shared_uuid, 14.55, "hash-fallback-key", False)  
    ]
    
    with TestClient(app) as client:
        test_amount = 14.55 
        
        # Action 1: Create
        response = client.post("/orders/", json={"amount": test_amount})
        assert response.status_code == 201
        data = response.json()
        assert data["is_existing"] is False
        assert "idempotency_key" in data
        
        # Action 2: Duplicate exact request simulating accidental double click
        duplicate_response = client.post("/orders/", json={"amount": test_amount})
        assert duplicate_response.status_code == 200
        
        dup_data = duplicate_response.json()
        assert dup_data["is_existing"] is True
        assert dup_data["order_id"] == data["order_id"]

def test_create_order_with_explicit_idempotency_key(mock_db_connection):
    """Test explicit client-side idempotency keys strictly mock 201/200 yields without touching prod databases."""
    shared_uuid = uuid.uuid4()
    explicit_key = f"test-key-{uuid.uuid4()}"
    
    mock_db_connection.fetchrow.side_effect = [
        generate_db_mock(shared_uuid, 25.00, explicit_key, True),
        generate_db_mock(shared_uuid, 25.00, explicit_key, False)
    ]
    
    with TestClient(app) as client:
        payload = {"amount": 25.00, "idempotency_key": explicit_key}
        
        # Action 1: Create
        response = client.post("/orders/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["idempotency_key"] == explicit_key
        assert data["is_existing"] is False
        
        # Action 2: Duplicate exact request simulating accidental double click
        duplicate_response = client.post("/orders/", json=payload)
        assert duplicate_response.status_code == 200
        
        dup_data = duplicate_response.json()
        assert dup_data["is_existing"] is True
        assert dup_data["order_id"] == data["order_id"]

# ===============================================
# FAILURE & EDGE CASES (422 / 500)
# ===============================================

def test_create_order_invalid_amount_fails_validation():
    """Test Pydantic cleanly rejects negative math returning HTTP 422 before targeting DB."""
    with TestClient(app) as client:
        # Action 1: Negative amount validation
        response = client.post("/orders/", json={"amount": -10.00})
        assert response.status_code == 422
        
        # Action 2: Zero amount validation
        response_zero = client.post("/orders/", json={"amount": 0})
        assert response_zero.status_code == 422

def test_hash_generation_failure_no_key_yields_500():
    """Test that an internal breakdown in Python's JSON/hashing strictly halts when no fallback key is available."""
    with TestClient(app) as client:
        with patch("app.services.order_service.hashlib.sha256", side_effect=Exception("Simulated hash crash")):
            
            # Action 1: Create triggering internal system crash
            response = client.post("/orders/", json={"amount": 50.00})
            assert response.status_code == 500
            assert "Idempotency key generation failed" in response.json()["detail"]

def test_hash_generation_failure_survives_with_explicit_key(mock_db_connection):
    """Test that if hashing crashes but the client provided a safety key, it survives completely using a mocked DB completion."""
    explicit_key = f"survival-key-{uuid.uuid4()}"
    shared_uuid = uuid.uuid4()
    
    mock_db_connection.fetchrow.return_value = generate_db_mock(shared_uuid, 50.00, explicit_key, True)
    
    with TestClient(app) as client:
        with patch("app.services.order_service.hashlib.sha256", side_effect=Exception("Simulated hash crash")):
            
            # Action 1: Create surviving internal system crash
            response = client.post("/orders/", json={"amount": 50.00, "idempotency_key": explicit_key})
            assert response.status_code == 201

def test_db_postgres_rejection_yields_500(mock_db_connection):
    """Test strict HTTP 500 mapping when Postgres throws a physical database-layer error."""
    mock_db_connection.fetchrow.side_effect = asyncpg.exceptions.DataError("Mocked Postgres Error")
    
    with TestClient(app) as client:
        # Action 1: Create triggering Postgres engine rejection
        response = client.post("/orders/", json={"amount": 10.00})
        assert response.status_code == 500

def test_db_unexpected_system_error_yields_500(mock_db_connection):
    """Test totally unpredictable catastrophic system errors bubble to 500 cleanly."""
    mock_db_connection.fetchrow.side_effect = Exception("Wildcard Memory Blowout")
    
    with TestClient(app) as client:
        # Action 1: Create triggering catastrophic Python hardware limit panic
        response = client.post("/orders/", json={"amount": 10.00})
        assert response.status_code == 500

def test_db_returns_no_row_data_yields_500(mock_db_connection):
    """Test failsafe where database successfully executed but bizarrely returned completely empty payload."""
    mock_db_connection.fetchrow.return_value = None
    
    with TestClient(app) as client:
        # Action 1: Create triggering silent Postgres return logic corruption
        response = client.post("/orders/", json={"amount": 10.00})
        assert response.status_code == 500
