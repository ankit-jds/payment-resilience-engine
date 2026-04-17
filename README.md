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
- `POST /orders`: **Generates Intents.** Atomic, idempotent generation of the parent checkout (Maps to Stripe `PaymentIntents` or Razorpay `Orders`).
- `POST /payments`: **Executes Payments (The Simulator).** Acts as the "World Simulator", mechanically replicating the Frontend SDK capturing the card, the Gateway processing the funds, and dynamically dispatching network-lossy Webhooks in the background.
- `POST /webhook`: **The State Machine.** Uses `SELECT ... FOR UPDATE` row-locks to sequentially process incoming webhook events safely.

### Eliminated Edge Cases
1. **Duplicate requests (Double clicks)**: Blocked cleanly by `INSERT ... ON CONFLICT (idempotency_key)`.
2. **Concurrent webhook races**: Forcefully queued natively via PostgreSQL row-level locks. 
3. **Webhook delay (Double charging)**: Order updates strictly use `WHERE status != 'PAID'`. If the query updates 0 rows, the webhook inherently triggers an auto-refund.
4. **Worker crashes**: Webhook logic explicitly decouples the physical receipt of duplicate payments from the network-bound processing of external refunds via the Daemon worker.


### Background Workers (Safety Nets) & Infrastructure
- **Refund Daemon**: A continuous polling worker safely processing Gateway reversals using strictly atomic states avoiding parallel queue overlap natively.
- **Reconciliation Cron**: A generic truth-checking loop querying the simulated payment provider directly to natively force-fulfill payments blocked by permanently dropped physical webhooks.
- **Container Architecture**: The background workers are physically deployed via `docker-compose` into isolated Crash Domains natively avoiding API downtime if background loops OOM gracefully.

### Testing Strategy
- **Offline Sandbox**: Using `pytest` and `anyio` to run fast, offline tests. A global fixture mocks `asyncpg` (the database connection) so we can easily test edge cases like network failures and database errors without needing a live database.
- **Live Integration**: End-to-end tests that connect directly to a live database to verify real-world scenarios (like idempotency collisions and duplicate webhooks).

## Remaining Work

As per the technical specification, the core engine, state machines, containerizations, and exhaustive resilience integrations are entirely natively implemented.

### 1. Redis Queue Infrastructure
While the background loops currently operate via robust PostgreSQL polling safely, shifting execution into an explicit Redis-backed worker structure (e.g. Celery / ARQ) is definitively scoped to scale massive horizontal throughput natively.

### 2. Cryptographic HMAC Implementation
For physical production deployments, the generic webhook routing engine must integrate an explicit `HMAC-SHA256` middleware layer verifying gateway signature headers explicitly blocking forged JSON payload insertions.
