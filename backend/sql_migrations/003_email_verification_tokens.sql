-- SupportFlow AI: Hashed customer email verification tokens
-- Additive schema preparation. No existing customer data changes.
-- Requires prior customer email_verified_at migration.

BEGIN;

CREATE TABLE IF NOT EXISTS public.email_verification_tokens (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES public.customers(id),
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_sent_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consumed_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_email_verification_customer
        UNIQUE (customer_id),
    CONSTRAINT uq_email_verification_token_hash
        UNIQUE (token_hash)
);

COMMIT;
