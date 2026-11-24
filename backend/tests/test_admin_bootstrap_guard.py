"""Pure safety-guard tests; no real database access."""

import pytest

from provision_first_admin import ensure_bootstrap_allowed


def test_empty_target_database_accepted():
    ensure_bootstrap_allowed(
        "supportflow_db",
        "supportflow_db",
        True,
        0,
    )


def test_wrong_database_rejected():
    with pytest.raises(RuntimeError):
        ensure_bootstrap_allowed(
            "production_db",
            "development_db",
            True,
            0,
        )


def test_missing_admin_table_rejected():
    with pytest.raises(RuntimeError):
        ensure_bootstrap_allowed(
            "supportflow_db",
            "supportflow_db",
            False,
            0,
        )


def test_existing_admin_rejected():
    with pytest.raises(RuntimeError):
        ensure_bootstrap_allowed(
            "supportflow_db",
            "supportflow_db",
            True,
            1,
        )


def test_test_database_rejected():
    with pytest.raises(RuntimeError):
        ensure_bootstrap_allowed(
            "supportflow_test_db",
            "supportflow_test_db",
            True,
            0,
        )

def test_matching_unapproved_database_rejected():
    with pytest.raises(RuntimeError):
        ensure_bootstrap_allowed(
            "some_other_database",
            "some_other_database",
            True,
            0,
        )


def test_configured_database_name_rejected_when_unapproved(monkeypatch):
    from provision_first_admin import validate_configured_database
    from app.config import settings

    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/other_db",
    )

    with pytest.raises(RuntimeError):
        validate_configured_database("supportflow_db")


def test_configured_database_guard_accepts_approved_target(monkeypatch):
    from provision_first_admin import validate_configured_database
    from app.config import settings

    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/supportflow_db",
    )

    validate_configured_database("supportflow_db")
