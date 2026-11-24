-- SupportFlow AI: Customer email verification
-- Additive migration only. Existing customers stay unverified.
-- Apply only after checking the target database.

BEGIN;

ALTER TABLE public.customers
ADD COLUMN IF NOT EXISTS
email_verified_at TIMESTAMPTZ;

COMMIT;
