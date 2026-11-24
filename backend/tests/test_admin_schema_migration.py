
"""Static SQL checks only. Never executes migrations."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "sql_migrations"
    / "006_admin_users_security_constraints.sql"
)


def sql_statements():
    content = MIGRATION.read_text(encoding="utf-8")

    # Remove full-line SQL comments before assertions.
    active_lines = [
        line
        for line in content.splitlines()
        if line.strip()
        and not line.lstrip().startswith("--")
    ]

    return "\n".join(active_lines).strip()


def test_migration_is_transactional():
    sql = sql_statements()

    assert sql.startswith("BEGIN;")
    assert sql.endswith("COMMIT;")


def test_migration_restricts_database_and_existing_admins():
    sql = sql_statements()

    assert "current_database() <> 'supportflow_db'" in sql
    assert "to_regclass('public.admin_users')" in sql
    assert "LOCK TABLE public.admin_users" in sql
    assert "EXISTS (SELECT 1 FROM public.admin_users)" in sql


def test_migration_defines_both_security_checks():
    sql = sql_statements()

    assert "admin_users_role_check" in sql
    assert "role IN ('admin', 'super_admin')" in sql

    assert "admin_users_session_version_check" in sql
    assert "CHECK (session_version >= 0)" in sql

    assert sql.count("ADD CONSTRAINT") == 2
