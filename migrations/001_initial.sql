CREATE TABLE orders (
    order_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    request_hash    VARCHAR(255) NOT NULL,
    provider_order_id VARCHAR(255),
    amount          NUMERIC(10, 2) NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'CREATED',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE payments (
    payment_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id    UUID NOT NULL REFERENCES orders(order_id),
    provider_payment_id VARCHAR(255) UNIQUE,
    status      VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    is_canonical BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE refunds (
    refund_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id  UUID NOT NULL REFERENCES payments(payment_id),
    provider_refund_id VARCHAR(255) UNIQUE,
    status      VARCHAR(50) NOT NULL DEFAULT 'PENDING_CONFIRMATION',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);