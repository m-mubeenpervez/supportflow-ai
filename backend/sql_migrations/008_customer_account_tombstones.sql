-- Option A: preserve customer identity key for existing tickets/orders while
-- explicitly marking the profile removed. Never run against original DB.
ALTER TABLE public.customers
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz NULL;
CREATE INDEX IF NOT EXISTS idx_customers_deleted_at
    ON public.customers (deleted_at);
