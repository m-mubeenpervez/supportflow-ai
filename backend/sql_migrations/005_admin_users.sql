-- SupportFlow AI: separate administrator identities
-- Additive migration. Does not modify customer records.
-- Apply only after review and database backup.

BEGIN;

CREATE TABLE IF NOT EXISTS public.admin_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    session_version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_admin_users_role
        CHECK (role IN ('admin', 'super_admin')),

    CONSTRAINT ck_admin_users_session_version
        CHECK (session_version >= 0)
);

COMMIT;
