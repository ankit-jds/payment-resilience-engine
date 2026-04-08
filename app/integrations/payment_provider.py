import asyncio
import random
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

async def create_order(order_id: str) -> dict:
    """
    Simulates creating an Order on the Gateway side (e.g., Razorpay Orders or Stripe Intents).
    External gateways mathematically require generating their own Order IDs before payments can begin.
    """
    artificial_delay = random.uniform(0.1, 0.4)
    await asyncio.sleep(artificial_delay)
    
    # Gateway order generation realistically resolves instantly but occasionally physically drops packets
    outcome = random.choices(["SUCCESS", "TIMEOUT"], weights=[0.95, 0.05], k=1)[0]
    
    if outcome == "TIMEOUT":
        logger.warning(f"[GATEWAY SIM] TIMEOUT: Network 504 lockup completely disconnecting Order generation.")
        return {"status": "TIMEOUT", "provider_order_id": None}
    
    provider_order_id = f"prov_order_{order_id.replace('-', '')[:16]}"
    logger.info(f"[GATEWAY SIM] ORDER CREATED: Generated provider lock {provider_order_id}")
    return {"status": "SUCCESS", "provider_order_id": provider_order_id}


async def process_refund(payment_id: str) -> dict:
    """
    Simulates executing an HTTP POST to the Gateway's distinct /refunds endpoint.
    Structurally separate from payments because banking networks parse reversed funds 
    using entirely disparate geographic routes internally.
    """
    artificial_delay = random.uniform(0.3, 0.8)
    await asyncio.sleep(artificial_delay)

    # Refunds logically succeed more often than payments because bank fraud traps are already cleared
    outcome = random.choices(["SUCCESS", "FAILED", "TIMEOUT"], weights=[0.85, 0.10, 0.05], k=1)[0]
    provider_refund_id = f"prov_ref_{payment_id.replace('-', '')[:16]}"

    if outcome == "SUCCESS":
        logger.info(f"[REFUND SIM] SUCCESS: Payment {payment_id} cleanly clawed back mapping {provider_refund_id}.")
    elif outcome == "FAILED":
        logger.info(f"[REFUND SIM] FAILED: Gateway explicitly rejected refund transmission mapping {provider_refund_id}.")
    elif outcome == "TIMEOUT":
        logger.warning(f"[REFUND SIM] TIMEOUT: Refund API handshake dropped via 504 lockup. Connection aborted.")
        return {"status": outcome, "provider_refund_id": None}

    return {"status": outcome, "provider_refund_id": provider_refund_id}


async def process_payment(
    payment_id: str,
    probabilities: Optional[Dict[str, float]] = None
) -> dict:
    """
    Simulates executing an external checkout against a Payment Gateway (e.g., Stripe, Bank APIs).
    Returns complex json object states parsing explicitly modeled Provider ID tags.
    """
    if probabilities is None:
        # Default distribution mappings precisely tracking realistic test environments
        probabilities = {
            "SUCCESS": 0.70,
            "FAILED": 0.20,
            "TIMEOUT": 0.10
        }

    # 1. Replicate physical inter-server network latency natively (200ms to 900ms variance)
    artificial_delay = random.uniform(0.2, 0.9)
    await asyncio.sleep(artificial_delay)

    # 2. Programmatically select mapped outcome cleanly wrapping Python's Weighted Random generator
    states = list(probabilities.keys())
    weights = list(probabilities.values())
    
    outcome = random.choices(states, weights=weights, k=1)[0]
    
    provider_payment_id = f"prov_pay_{payment_id.replace('-', '')[:16]}"
    
    # 3. Log transparently dynamically proving routing behavior in terminals cleanly
    if outcome == "SUCCESS":
        logger.info(f"[PAYMENT SIM] SUCCESS: Intent {payment_id} cleanly processed mapping {provider_payment_id}.")
    elif outcome == "FAILED":
        logger.info(f"[PAYMENT SIM] FAILED: Intent {payment_id} declined remotely mapping {provider_payment_id}.")
    elif outcome == "TIMEOUT":
        logger.warning(f"[PAYMENT SIM] TIMEOUT: Network 504 lockup evaluating {payment_id}. Connection violently aborted.")
        return {"status": outcome, "provider_payment_id": None}

    return {"status": outcome, "provider_payment_id": provider_payment_id}
