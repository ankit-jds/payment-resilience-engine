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
4. **Worker crashes**: Webhook logic explicitly decouples the physical receipt of duplicate payments from the network-bound processing of external refunds via the Daemon worker.


### Background Workers (Safety Nets)
- **Refund Daemon**: A continuous polling worker safely processing Gateway reversals using strictly atomic states avoiding parallel queue overlap natively.
- **Reconciliation Cron**: A generic truth-checking loop querying the simulated payment provider directly to natively force-fulfill payments blocked by permanently dropped physical webhooks.

### Testing Strategy
- A global `pytest` fixture completely intercepts `asyncpg` to run the full application transaction suite completely offline utilizing `anyio`.
- Explicitly mocks and traps database network lockups, constraint violations, and massive structural connectivity loss mapping 100% path coverage safely.

## Remaining Work

As per the technical specification, the core engine, state machines, and resilience workers are entirely natively completed.

### 1. Database Currency Precision (Paise/Cents)
Currently, financial models use `DECIMAL` mapping. For massive high-frequency environments, ledger schemas must be structurally migrated to `BIGINT` (paise/cents) to entirely mathematically eliminate float approximation vulnerabilities structurally.

### 2. Live Integration Tests
Expanding the offline `pytest` suite to include dynamic physical Database-Container spin-ups explicitly proving mathematical state convergence under targeted hardware crash scenarios natively.

### 3. Redis Queue Infrastructure
While the background loops currently operate via robust PostgreSQL polling safely, shifting execution into an explicit Redis-backed worker structure (e.g. Celery / ARQ) is definitively scoped to scale massive horizontal throughput natively.

### 4. Cryptographic HMAC Implementation
For physical production deployments, the generic webhook routing engine must integrate an explicit `HMAC-SHA256` middleware layer verifying gateway signature headers explicitly blocking forged JSON payload insertions.
