-- SupportFlow AI: Encrypted verification email outbox
-- Additive migration only.
-- No existing customer, ticket or notification records changed.
-- Apply only after reviewing the database target.

BEGIN;

CREATE TABLE IF NOT EXISTS public.verification_email_outbox (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES public.customers(id),
    token_hash VARCHAR(64) NOT NULL,
    encrypted_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claim_token VARCHAR(36),
    lease_expires_at TIMESTAMPTZ,
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_verification_email_outbox_customer
        UNIQUE (customer_id)
);

CREATE INDEX IF NOT EXISTS
ix_verification_email_outbox_pending
ON public.verification_email_outbox
(next_attempt_at, id)
WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS
ix_verification_email_outbox_leases
ON public.verification_email_outbox
(lease_expires_at, id)
WHERE status = 'processing';

COMMIT;
