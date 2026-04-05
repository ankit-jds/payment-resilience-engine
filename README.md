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

*Architecture, design decisions, and API docs will be added as the system is built.*
