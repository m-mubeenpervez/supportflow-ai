-- SupportFlow AI: admin_users security constraints.
-- Review and execute separately after an approved backup.
-- This file is NOT executed by its creation tests.

BEGIN;

DO $$
BEGIN
    IF current_database() <> 'supportflow_db' THEN
        RAISE EXCEPTION 'Unapproved database';
    END IF;

    IF to_regclass('public.admin_users') IS NULL THEN
        RAISE EXCEPTION 'admin_users table missing';
    END IF;
END
$$;

LOCK TABLE public.admin_users IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.admin_users) THEN
        RAISE EXCEPTION
            'Admin accounts already exist; manual review required';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.admin_users'::regclass
          AND conname IN (
              'admin_users_role_check',
              'admin_users_session_version_check'
          )
    ) THEN
        RAISE EXCEPTION
            'One or more target constraints already exist';
    END IF;
END
$$;

ALTER TABLE public.admin_users
    ADD CONSTRAINT admin_users_role_check
    CHECK (role IN ('admin', 'super_admin'));

ALTER TABLE public.admin_users
    ADD CONSTRAINT admin_users_session_version_check
    CHECK (session_version >= 0);

COMMIT;
