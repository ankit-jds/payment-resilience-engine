import uuid
import pytest
import asyncpg
from unittest.mock import patch, AsyncMock, MagicMock
from app.workers.reconciliation_worker import execute_reconciliation_sweep

@pytest.fixture
def mock_pool():
    """Build a complete offline replica pool mapping safely for hit-and-run tests natively."""
    pool = MagicMock()
    mock_acquire_context = AsyncMock()
    mock_conn = AsyncMock()
    
    # Setup Connection Tree
    pool.acquire.return_value = mock_acquire_context
    mock_acquire_context.__aenter__.return_value = mock_conn
    
    # Setup Transaction Tree
    mock_transaction_context = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_transaction_context)
    
    return pool, mock_conn

@pytest.mark.anyio
@patch("app.workers.reconciliation_worker.check_payment_status")
@patch("app.workers.reconciliation_worker.process_webhook_payload")
async def test_reconciliation_sweep_payment_success_recovery(mock_webhook, mock_check, mock_pool):
    """Test that a PENDING ghost discovered as SUCCESS on the gateway dynamically generates a recovery Webhook!"""
    pool, mock_conn = mock_pool
    payment_uuid = uuid.uuid4()
    
    # Phase 1 DB Mock: Return 1 Ghost Payment!
    # Phase 2 DB Mock: Return 0 Stuck Refunds.
    mock_conn.fetch.side_effect = [
        [{"payment_id": payment_uuid}],
        []
    ]
    
    # The external Gateway mock tells the worker: "Actually, this succeeded!"
    mock_check.return_value = {"status": "SUCCESS"}
    
    await execute_reconciliation_sweep(pool)
    
    # Verify the Hit-And-Run Gateway execution fired exactly once
    mock_check.assert_called_once_with(str(payment_uuid))
    
    # Verify the Worker mathematically crafted a synthetic Webhook Payload to force fulfillment
    mock_webhook.assert_called_once()
    payload = mock_webhook.call_args[0][1]
    assert payload.event_type == "payment.updated"
    assert payload.status == "SUCCESS"
    assert str(payload.payment_id) == str(payment_uuid)


@pytest.mark.anyio
@patch("app.workers.reconciliation_worker.check_payment_status")
async def test_reconciliation_sweep_payment_abandoned_purge(mock_check, mock_pool):
    """Test that a PENDING ghost discovered as FAILED correctly purges the payment and drops orphaned Orders."""
    pool, mock_conn = mock_pool
    payment_uuid = uuid.uuid4()
    
    # Phase 1 DB Mock: 1 Ghost. Phase 2: 0 Refunds.
    mock_conn.fetch.side_effect = [
        [{"payment_id": payment_uuid}],
        []
    ]
    
    # The external Gateway mock tells the worker: "User abandoned the checkout entirely."
    mock_check.return_value = {"status": "FAILED"}
    
    await execute_reconciliation_sweep(pool)
    
    # Verify the worker aggressively executed structural DROP commands!
    assert mock_conn.execute.call_count == 2
    
    calls = mock_conn.execute.call_args_list
    assert "UPDATE payments SET status = 'FAILED'" in calls[0][0][0]
    assert "UPDATE orders o\n                            SET status = 'FAILED'" in calls[1][0][0]
    

@pytest.mark.anyio
@patch("app.workers.reconciliation_worker.check_refund_status")
@patch("app.workers.reconciliation_worker.process_webhook_payload")
async def test_reconciliation_sweep_refund_success_recovery(mock_webhook, mock_check, mock_pool):
    """Test that a stuck Refund discovered dynamically resolved manually forcefully builds a refund hook natively."""
    pool, mock_conn = mock_pool
    payment_uuid = uuid.uuid4()
    
    # Phase 1 DB Mock: 0 Ghosts.
    # Phase 2 DB Mock: 1 Stuck Refund.
    mock_conn.fetch.side_effect = [
        [],
        [{"payment_id": payment_uuid}]
    ]
    
    # Gateway API Mock: Refund physically cleared across banking rails!
    mock_check.return_value = {"status": "SUCCESS"}
    
    await execute_reconciliation_sweep(pool)
    
    mock_check.assert_called_once_with(str(payment_uuid))
    
    mock_webhook.assert_called_once()
    payload = mock_webhook.call_args[0][1]
    assert payload.event_type == "refund.updated"
    assert payload.status == "SUCCESS"

@pytest.mark.anyio
@patch("app.workers.reconciliation_worker.check_refund_status")
async def test_reconciliation_sweep_refund_failed_escalation(mock_check, mock_pool):
    """Test that a stuck Refund discovered completely dead logically escalates to FAILED locking intervention."""
    pool, mock_conn = mock_pool
    payment_uuid = uuid.uuid4()
    
    mock_conn.fetch.side_effect = [
        [],
        [{"payment_id": payment_uuid}]
    ]
    
    # Gateway API Mock: Refund failed permanently on banking rails!
    mock_check.return_value = {"status": "FAILED"}
    
    await execute_reconciliation_sweep(pool)
    
    mock_check.assert_called_once_with(str(payment_uuid))
    
    mock_conn.execute.assert_called_once()
    assert "UPDATE refunds SET status = 'FAILED'" in mock_conn.execute.call_args[0][0]

@pytest.mark.anyio
async def test_reconciliation_sweep_db_fetch_exception_handled(mock_pool):
    """Test that a catastrophic Database disconnect during Phase 1 safely continues into Phase 2 natively."""
    pool, mock_conn = mock_pool
    
    # Force Phase 1 to brutally crash, Phase 2 to return empty array!
    mock_conn.fetch.side_effect = [
        Exception("Database violently crashed during Phase 1 Ghost Sweep!"),
        []
    ]
    
    # The worker should flawlessly swallow the Exception, log it, and continue the execution loop gracefully.
    try:
        await execute_reconciliation_sweep(pool)
        assert True, "Worker gracefully survived massive internal DB disconnect."
    except Exception:
        pytest.fail("Worker structurally collapsed instead of catching native fetch exception.")
