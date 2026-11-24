-- Apply ONLY to the recovered supportflow_recovery database after backup.
-- Independent of ticket-bound notification outbox.
CREATE TABLE IF NOT EXISTS public.customer_action_email_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_key VARCHAR(160) NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES public.customers(id),
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('deactivated', 'activated', 'removed')),
    recipient_email VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claim_token VARCHAR(36),
    lease_expires_at TIMESTAMPTZ,
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_account_action_status CHECK (
      status IN ('pending','retry','processing','sent','failed','cancelled')
    )
);
CREATE INDEX IF NOT EXISTS idx_customer_action_email_due
 ON public.customer_action_email_outbox (next_attempt_at, id)
 WHERE status IN ('pending', 'retry', 'processing');
