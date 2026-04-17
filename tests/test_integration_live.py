import pytest
import uuid
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

# ==============================================================================
# LIVE PHYSICAL INTEGRATION SUITE (EXHAUSTIVE PERMUTATIONS)
# ==============================================================================
# WARNING: These tests DO NOT USE MOCKS for the DATABASE. They establish literal 
# physical TCP connections to your Cloud Database (Supabase) via the TestClient lifespan!
#
# However, we strictly mock the Payment Provider randomizations to prevent chaotic 
# 504 Network Timeout simulations from breaking our deterministic database testing!
# ==============================================================================

@pytest.fixture(autouse=True)
def mock_background_simulation():
    """
    Globally trap the background task that normally simulates chaotic frontend/webhook 
    latency and 70% random drop rates. We make it completely deterministic by instantly 
    assigning a provider UUID, but we PREVENT it from randomly firing webhooks natively 
    so our explicit TestClient permutations don't race against background async loops!
    """
    async def deterministic_simulation(pool, payment_id):
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE payments SET provider_payment_id = $1 WHERE payment_id = $2",
                f"prov_mock_{str(uuid.uuid4())[:8]}", payment_id
            )
            
    with patch("app.services.payment_service._bg_simulate_frontend_and_webhook", side_effect=deterministic_simulation):
        yield

@pytest.mark.anyio
async def test_end_to_end_payment_success_and_race_condition():
    """Permutation 1: Complete Intent -> Execution -> Success Webhook -> Race Condition Dropped."""
    with TestClient(app) as client:
        # 1. GENERATE INTENT
        order_key = f"live-test-{uuid.uuid4()}"
        order_res = client.post("/orders/", json={"amount": 5000, "idempotency_key": order_key})
        order_id = order_res.json()["order_id"]
        
        # 2. EXECUTE PAYMENT
        pay_res = client.post("/payments/", json={"order_id": order_id})
        payment_id = pay_res.json()["payment_id"]
        
        # 3. WEBHOOK ARRIVES (SUCCESS)
        hook_res = client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": payment_id,
            "status": "SUCCESS",
            "amount_captured": 5000
        })
        assert hook_res.status_code == 200
        
        # 4. RACE CONDITION WEBHOOK (DUPLICATE)
        hook_res_dup = client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": payment_id,
            "status": "SUCCESS",
            "amount_captured": 5000
        })
        assert hook_res_dup.status_code == 200
        assert "securely skipped" in hook_res_dup.json()["message"] or "isolated" in hook_res_dup.json()["message"]


@pytest.mark.anyio
async def test_end_to_end_security_1_cent_flaw():
    """Permutation 2: Zero-Trust Architecture blocks payload amount manipulation."""
    with TestClient(app) as client:
        order_res = client.post("/orders/", json={"amount": 10000, "idempotency_key": f"hack-{uuid.uuid4()}"})
        pay_res = client.post("/payments/", json={"order_id": order_res.json()["order_id"]})
        
        # HACKER WEBHOOK (100 paise captured for a 10000 paise order)
        hook_res = client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": pay_res.json()["payment_id"],
            "status": "SUCCESS",
            "amount_captured": 100
        })
        assert hook_res.status_code == 400
        assert "Security violation" in hook_res.json()["detail"]


@pytest.mark.anyio
async def test_end_to_end_idempotency_collision_recovery():
    """Permutation 3: Network stutters causing identical Order Intent payloads to fire twice."""
    with TestClient(app) as client:
        shared_key = f"stutter-key-{uuid.uuid4()}"
        
        # FIRST REQUEST
        res1 = client.post("/orders/", json={"amount": 2500, "idempotency_key": shared_key})
        assert res1.status_code == 201
        order_id_1 = res1.json()["order_id"]
        
        # SECOND IDENTICAL REQUEST (User double-clicked 'Checkout')
        res2 = client.post("/orders/", json={"amount": 2500, "idempotency_key": shared_key})
        assert res2.status_code == 200  # Note: HTTP 200 (OK returned existing), NOT 201 (Created new)
        order_id_2 = res2.json()["order_id"]
        
        # System natively returned the exact same lock!
        assert order_id_1 == order_id_2


@pytest.mark.anyio
async def test_end_to_end_multiple_payment_executions_allowed():
    """Permutation 4: User double-clicks 'Pay Now' for the same order intent."""
    with TestClient(app) as client:
        order_res = client.post("/orders/", json={"amount": 3000, "idempotency_key": f"pay-dup-{uuid.uuid4()}"})
        order_id = order_res.json()["order_id"]
        
        # FIRST EXECUTION
        pay1 = client.post("/payments/", json={"order_id": order_id})
        assert pay1.status_code == 201
        
        # SECOND EXECUTION (Simulating frontend race condition)
        pay2 = client.post("/payments/", json={"order_id": order_id})
        
        # The architecture natively ALLOWS multiple payment intents per order (resolved canonically by webhooks!)
        assert pay2.status_code == 201
        assert pay1.json()["payment_id"] != pay2.json()["payment_id"]


@pytest.mark.anyio
async def test_end_to_end_webhook_failed_trajectory():
    """Permutation 5: Gateway explicitly sends a FAILED physical payload."""
    with TestClient(app) as client:
        order_res = client.post("/orders/", json={"amount": 4000, "idempotency_key": f"fail-traj-{uuid.uuid4()}"})
        pay_res = client.post("/payments/", json={"order_id": order_res.json()["order_id"]})
        
        hook_res = client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": pay_res.json()["payment_id"],
            "status": "FAILED",
            "amount_captured": 0  # Gateway captured nothing
        })
        
        assert hook_res.status_code == 200
        assert "locked into FAILED state perfectly" in hook_res.json()["message"]


@pytest.mark.anyio
async def test_end_to_end_webhook_ghost_payload_rejection():
    """Permutation 6: Gateway sends a webhook for a Payment UUID that doesn't exist in our DB."""
    with TestClient(app) as client:
        ghost_uuid = str(uuid.uuid4())
        
        hook_res = client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": ghost_uuid,
            "status": "SUCCESS",
            "amount_captured": 1000
        })
        
        # System cleanly 404s the ghost payload instead of 500 crashing
        assert hook_res.status_code == 404


@pytest.mark.anyio
async def test_end_to_end_webhook_malicious_downgrade_rejection():
    """Permutation 7: Gateway attempts to mark a previously 'SUCCESS' payment back to 'PENDING/FAILED'."""
    with TestClient(app) as client:
        order_res = client.post("/orders/", json={"amount": 9000, "idempotency_key": f"downgrade-{uuid.uuid4()}"})
        pay_res = client.post("/payments/", json={"order_id": order_res.json()["order_id"]})
        payment_id = pay_res.json()["payment_id"]
        
        # 1. Successful Webhook completes the transaction
        client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": payment_id,
            "status": "SUCCESS",
            "amount_captured": 9000
        })
        
        # 2. Delayed out-of-order Webhook arrives claiming it's FAILED
        hook_downgrade = client.post("/webhook/", json={
            "event_type": "payment.updated",
            "payment_id": payment_id,
            "status": "FAILED",
            "amount_captured": 0
        })
        
        # The structural lock natively drops state regressions
        assert hook_downgrade.status_code == 200
        assert "skipped" in hook_downgrade.json()["message"].lower() or "isolated" in hook_downgrade.json()["message"].lower()
