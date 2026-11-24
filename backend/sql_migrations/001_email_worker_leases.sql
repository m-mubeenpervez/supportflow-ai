-- SupportFlow AI: Email worker lease fields
-- Additive migration only.
-- Run only after verifying the target database.
-- Does not delete or reset existing data.

BEGIN;

ALTER TABLE email_outbox
    ADD COLUMN IF NOT EXISTS claim_token VARCHAR(36);

ALTER TABLE email_outbox
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_email_outbox_pending_due
    ON email_outbox (next_attempt_at, id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS ix_email_outbox_lease_expiry
    ON email_outbox (lease_expires_at, id)
    WHERE status = 'processing';

COMMIT;
