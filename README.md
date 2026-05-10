# Payment Consistency Engine

Payment systems fail in ways that are invisible until money is involved.  
This is a backend implementation of consistency guarantees that keep payments correct under failure.

**Status: In progress**

---

## Stack

- FastAPI + asyncpg + PostgreSQL
- Raw SQL only — no ORM
- Simulated payment provider

---

## Patterns being implemented

- Idempotency
- Race condition handling
- Retry logic
- Webhook resilience
- Eventual consistency

---

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

---

### Data Model Constraints

Database-level constraints guarantee data integrity even if the Python application layer crashes:

- `orders`: `idempotency_key` is UNIQUE to cleanly catch double-order generation.
- `payments`: Foreign keys tightly decouple payment attempts from orders.
- `refunds`: `payment_id` is UNIQUE, guaranteeing refund pipelines are strictly idempotent.

---

### Implemented APIs

- `POST /orders`: **Generates Intents.** Atomic, idempotent generation of the parent checkout (maps to Stripe PaymentIntents or Razorpay Orders).
- `POST /payments`: **Executes Payments (The Simulator).** Simulates frontend SDK capture, gateway processing, and lossy webhook dispatch.
- `POST /webhook`: **The State Machine.** Uses `SELECT ... FOR UPDATE` row-locks to process incoming webhook events safely.

---

### Eliminated Edge Cases

1. **Duplicate requests (Double clicks)**  
   Blocked cleanly by `INSERT ... ON CONFLICT (idempotency_key)`.

2. **Concurrent webhook races**  
   Forcefully queued via PostgreSQL row-level locks.

3. **Webhook delay (Double charging)**  
   Order updates strictly use `WHERE status != 'PAID'`. If the query updates 0 rows, the webhook triggers an auto-refund.

4. **Worker crashes**  
   Webhook logic decouples duplicate payment receipt from network-bound refund execution through daemon workers.

---

### Background Workers (Safety Nets) & Infrastructure

- **Refund Daemon**: A polling worker safely processing gateway reversals through atomic refund states.
- **Reconciliation Cron**: Queries the simulated provider directly to recover payments blocked by dropped webhooks.
- **Container Architecture**: Workers are deployed via `docker-compose` into isolated crash domains to avoid API downtime.

---

### Testing Strategy

- **Offline Sandbox**: Uses `pytest` and `anyio` with mocked `asyncpg` to simulate failures without a live database.
- **Live Integration**: End-to-end tests against a real database to verify idempotency collisions and duplicate webhook handling.

---

## Remaining Work

The core engine, state machines, and failure handling patterns are implemented. Remaining production-focused improvements:

### 1. Server-Sent Events (SSE) Integration

The backend currently exposes deterministic payment simulations through APIs, but event streaming for the visualization engine is not yet wired.

Production-facing simulation flows will expose structured Server-Sent Events (SSE) streams to the frontend, allowing real-time visualization of:

- State transitions
- Webhook arrivals
- Duplicate request handling
- Retry execution
- Refund queue processing
- Reconciliation recovery

This will make the simulation layer reflect backend truth directly instead of relying on mocked frontend event streams.

---

### 2. Redis Queue Infrastructure

Background workers currently rely on PostgreSQL polling.  
Migrating to Redis-backed workers (Celery / ARQ) will improve horizontal scalability.

---

### 3. Cryptographic HMAC Implementation

Production webhooks require explicit `HMAC-SHA256` verification to block forged payloads and guarantee provider authenticity.

