-- 002_update_amount_to_bigint.sql
-- Migration to mathematically completely eliminate floating-point approximation vulnerabilities
-- by shifting currency modeling to the lowest absolute integer fraction (cents/paise).

BEGIN;

ALTER TABLE orders 
    ALTER COLUMN amount TYPE BIGINT USING (amount * 100)::BIGINT;

COMMIT;
