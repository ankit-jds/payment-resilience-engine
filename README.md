# Payment Resilience Engine

Payment systems fail in ways that are invisible until money is involved.
This is a backend implementation of the patterns that prevent those failures.

**Status: In progress**

---

## Stack
- FastAPI + asyncpg + PostgreSQL
- Raw SQL only — no ORM
- Simulated payment provider

## Patterns being implemented
- Idempotency
- Race condition handling
- Retry logic  
- Webhook resilience
- Eventual consistency

## Out of scope / simulated
- Payment provider is simulated — no Stripe, Razorpay, or real money
- No PCI compliance
- No authentication / authorization
- No frontend
- Webhook delivery is simulated locally — no real HTTP callbacks from a provider

---

## What is built so far

This implements the core rules defined in the Failure-Resilient Payment Processing spec. The goal is correctness under failure, not scale. 

### Core Logic
To eliminate race conditions, the system permanently separates `Orders` from `Payments`:
- **One order per checkout**: Handled via hybrid idempotency keys.
- **Multiple payments per order**: Users can retry failed payments against the same order without issue.
- **Strict canonical winner**: The first payment to return a SUCCESS webhook locks the order as PAID.
- **Safe duplicate handling**: Any subsequent SUCCESS webhooks for an already-paid order are flagged as `DUPLICATE_SUCCESS` and funneled directly into a refund queue.

### Data Model Constraints
Database-level constraints guarantee data integrity even if the Python application layer crashes:
- `orders`: `idempotency_key` is UNIQUE to cleanly catch double-order generation.
- `payments`: Foreign keys tightly decouple payment attempts from orders.
- `refunds`: `payment_id` is UNIQUE, guaranteeing refund pipelines are strictly idempotent.

### Implemented APIs
- `POST /orders`: Atomic, idempotent order creation.
- `POST /payments`: Generates pending payment intents.
- `POST /webhook`: The state machine. Uses `SELECT ... FOR UPDATE` row-locks to sequentially process incoming webhook events safely.

### Eliminated Edge Cases
1. **Duplicate requests (Double clicks)**: Blocked cleanly by `INSERT ... ON CONFLICT (idempotency_key)`.
2. **Concurrent webhook races**: Forcefully queued natively via PostgreSQL row-level locks. 
3. **Webhook delay (Double charging)**: Order updates strictly use `WHERE status != 'PAID'`. If the query updates 0 rows, the webhook inherently triggers an auto-refund.
4. **Worker crashes**: Webhook logic explicitly decouples the physical receipt of duplicate payments from the network-bound processing of external refunds. 

### Testing Strategy
- A global `pytest` fixture completely intercepts `asyncpg` to run the full application transaction suite completely offline.
- Explicitly mocks and traps database network lockups, constraint violations, and missing DB payloads.

## Remaining Work

As per the technical specification, the core synchronous APIs and State Machines are completely implemented. The following asynchronous background systems remain:

### 1. Async Refund Worker (Section 10.6)
A background daemon that continuously polls the `refunds` table for `PENDING_CONFIRMATION` records, safely routes them to the Simulated Payment Provider, and maps the network result (`SUCCESS` or timeout retry).

### 2. Reconciliation Cron Job (Section 10.7)
A periodic safety-net service that forces eventual consistency cleanly:
- Sweeping `payments` stuck indefinitely in `PENDING` due to lost webhooks.
- Sweeping `refunds` indefinitely stuck in `PENDING_CONFIRMATION`.
- Triggering exponential backoff retries dynamically.

### 3. Redis Queue Infrastructure (Section 14)
While the refund loop currently operates via PostgreSQL polling safely, shifting the execution queues into an explicit Redis-backed worker structure is scoped to decouple scaling loads.

### 4. Live Integration Tests (Section 10.11)
Expanding the offline `pytest` suite to include literal database-container integrations proving physical state convergence under worker crash circumstances natively.
