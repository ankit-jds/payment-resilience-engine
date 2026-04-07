import uuid
import pytest
import asyncpg
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

def generate_payment_row_mock(status, order_id):
    """Helper generator to construct an asyncpg row mimicking the locked Payment select payload structure"""
    return {
        "status": status,
        "order_id": order_id
    }

# ===============================================
# CRITICAL BEST PRACTICES: GLOBAL FIXTURE
# ===============================================

@pytest.fixture(autouse=True)
def mock_db_connection():
    """
    Forcefully intercept the FastAPI Lifespan database pool startup. 
    """
    with patch("app.db.connection.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()  
        
        mock_acquire_context = AsyncMock()
        mock_conn = AsyncMock()
        
        # Link connections
        mock_pool.acquire.return_value = mock_acquire_context
        mock_acquire_context.__aenter__.return_value = mock_conn
        
        # Explicitly Mock the `async with conn.transaction():` context manager boundary natively
        mock_transaction_context = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=mock_transaction_context)
        
        mock_create_pool.return_value = mock_pool
        yield mock_conn

# ===============================================
# SUCCESS CASES (200 OK)
# ===============================================

def test_webhook_success_canonical_win(mock_db_connection):
    """Test standard SUCCESS webhook where the Payment uniquely locks the Order resulting in a Canonical WIN."""
    payment_uuid = uuid.uuid4()
    order_uuid = uuid.uuid4()
    
    # 1. First fetchrow safely locks the payment natively
    # 2. Second fetchrow locks the order updating status to PAID (returns order_id actively mapping 1 row)
    mock_db_connection.fetchrow.side_effect = [
        generate_payment_row_mock("PENDING", str(order_uuid)),
        {"order_id": str(order_uuid)}
    ]
    
    with TestClient(app) as client:
        # Action 1: Execute webhook payload
        response = client.post("/webhook/", json={"payment_id": str(payment_uuid), "status": "SUCCESS"})
        assert response.status_code == 200
        assert "Flawless canonical execution seamlessly triggered!" in response.json()["message"]
        
        # Validate exact SQL trace execution dynamically mapped updates cleanly
        mock_db_connection.execute.assert_called_once()
        call_args = mock_db_connection.execute.call_args[0]
        assert "is_canonical = TRUE" in call_args[0]

def test_webhook_success_duplicate_fallback(mock_db_connection):
    """Test SUCCESS webhook arriving incredibly late AFTER the parent order has already gracefully locked PAID."""
    payment_uuid = uuid.uuid4()
    order_uuid = uuid.uuid4()
    
    # First fetchrow unlocks the payment cleanly.
    # Second fetchrow attempts to update the order but returns entirely None cleanly trapping 0 row shifts!
    mock_db_connection.fetchrow.side_effect = [
        generate_payment_row_mock("PENDING", str(order_uuid)),
        None
    ]
    
    with TestClient(app) as client:
        # Action 1: Execute duplicate overlapped webhook payload
        response = client.post("/webhook/", json={"payment_id": str(payment_uuid), "status": "SUCCESS"})
        assert response.status_code == 200
        assert "Duplicate success rigorously isolated" in response.json()["message"]
        
        # Validate both Double Success flag AND Refund Intent logic sets were structurally inserted natively!
        assert mock_db_connection.execute.call_count == 2
        assert "is_canonical = FALSE" in mock_db_connection.execute.call_args_list[0][0][0]
        assert "INSERT INTO refunds" in mock_db_connection.execute.call_args_list[1][0][0]

def test_webhook_success_ignored_duplicate_ping(mock_db_connection):
    """Test external gateway redundantly firing exactly identically tracked SUCCESS webhooks twice natively skipping instantly."""
    payment_uuid = uuid.uuid4()
    
    # Simulate DB returning a payment that is ALREADY completely internally flagged SUCCESS!
    mock_db_connection.fetchrow.return_value = generate_payment_row_mock("SUCCESS", str(uuid.uuid4()))
    
    with TestClient(app) as client:
        response = client.post("/webhook/", json={"payment_id": str(payment_uuid), "status": "SUCCESS"})
        assert response.status_code == 200
        assert "Webhook securely skipped logically." in response.json()["message"]
        
        # Validate exactly ZERO execution modification locks fired safely.
        assert mock_db_connection.execute.call_count == 0

def test_webhook_failed_standard_rejection(mock_db_connection):
    """Test normal FAILED webhook firmly locking payment states completely leaving parent order untouched for robust retries."""
    payment_uuid = uuid.uuid4()
    
    mock_db_connection.fetchrow.return_value = generate_payment_row_mock("PENDING", str(uuid.uuid4()))
    
    with TestClient(app) as client:
        response = client.post("/webhook/", json={"payment_id": str(payment_uuid), "status": "FAILED"})
        assert response.status_code == 200
        assert "locked into FAILED state perfectly" in response.json()["message"]
        
        # Validate the FAILED SQL update ran exactly natively!
        mock_db_connection.execute.assert_called_once()
        assert "status = 'FAILED'" in mock_db_connection.execute.call_args[0][0]

def test_webhook_failed_no_state_regression(mock_db_connection):
    """Test Gateway bizarrely sending FAILED hook massively AFTER sending SUCCESS hook natively completely blocks data destruction!"""
    payment_uuid = uuid.uuid4()
    
    mock_db_connection.fetchrow.return_value = generate_payment_row_mock("SUCCESS", str(uuid.uuid4()))
    
    with TestClient(app) as client:
        response = client.post("/webhook/", json={"payment_id": str(payment_uuid), "status": "FAILED"})
        assert response.status_code == 200
        assert "Webhook rigorously skipped natively" in response.json()["message"]
        
        # Confirm absolutely no Database execute commands were destructively allowed to run!
        assert mock_db_connection.execute.call_count == 0

# ===============================================
# FAILURE & EDGE CASES (400 / 404 / 422 / 500)
# ===============================================

def test_webhook_invalid_status_aborted(mock_db_connection):
    """Test webhook payloads containing completely unmapped structural statuses completely abort 400 safely."""
    with TestClient(app) as client:
        response = client.post("/webhook/", json={"payment_id": str(uuid.uuid4()), "status": "RANDOM_GARBAGE"})
        assert response.status_code == 400
        assert "Invalid webhook status" in response.json()["detail"]

def test_webhook_unknown_payment_id_fails_404(mock_db_connection):
    """Test Gateway pinging our API heavily with completely unknown Payment IDs throws robust 404 blockades instantly."""
    mock_db_connection.fetchrow.return_value = None
    
    with TestClient(app) as client:
        response = client.post("/webhook/", json={"payment_id": str(uuid.uuid4()), "status": "SUCCESS"})
        assert response.status_code == 404
        assert "Webhook payload natively rejected" in response.json()["detail"]

def test_db_postgres_rejection_yields_500(mock_db_connection):
    """Test strict HTTP 500 mapping when Postgres physically throws a catastrophic database-layer connection wipe."""
    mock_db_connection.fetchrow.side_effect = asyncpg.exceptions.DataError("Mocked Postgres Disconnect")
    
    with TestClient(app) as client:
        response = client.post("/webhook/", json={"payment_id": str(uuid.uuid4()), "status": "SUCCESS"})
        assert response.status_code == 500
