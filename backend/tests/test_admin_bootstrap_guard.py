"""Pure safety-guard tests for the tracked first-admin bootstrap CLI."""

import pytest

from scripts import bootstrap_admin


def test_fresh_database_is_accepted(monkeypatch):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/fresh_supportflow",
    )
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "application_database_name",
        "fresh_supportflow",
    )
    assert bootstrap_admin.ensure_bootstrap_target_is_safe() == "fresh_supportflow"


@pytest.mark.parametrize("database", ["supportflow_recovery", "supportflow_test_db"])
def test_protected_databases_are_rejected(monkeypatch, database):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        f"postgresql+asyncpg://user:pass@localhost/{database}",
    )
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "application_database_name",
        database,
    )
    with pytest.raises(RuntimeError, match="protected"):
        bootstrap_admin.ensure_bootstrap_target_is_safe()


def test_missing_database_name_is_rejected(monkeypatch):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost",
    )
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "application_database_name",
        "fresh_supportflow",
    )
    with pytest.raises(RuntimeError, match="database name"):
        bootstrap_admin.ensure_bootstrap_target_is_safe()


def test_protected_configured_name_is_rejected_even_with_fresh_url(monkeypatch):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/fresh_supportflow",
    )
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "application_database_name",
        "supportflow_recovery",
    )
    with pytest.raises(RuntimeError, match="protected"):
        bootstrap_admin.ensure_bootstrap_target_is_safe()


def test_protected_database_match_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/SUPPORTFLOW_TEST_DB",
    )
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "application_database_name",
        "SUPPORTFLOW_TEST_DB",
    )
    with pytest.raises(RuntimeError, match="protected"):
        bootstrap_admin.ensure_bootstrap_target_is_safe()


def test_fresh_url_is_accepted_when_application_name_is_unset(monkeypatch):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/another_fresh_db",
    )
    monkeypatch.setattr(bootstrap_admin.settings, "application_database_name", "")
    assert bootstrap_admin.ensure_bootstrap_target_is_safe() == "another_fresh_db"


def test_database_name_is_returned_from_configured_url(monkeypatch):
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "database_url",
        "postgresql+asyncpg://user:pass@localhost/clone_database",
    )
    monkeypatch.setattr(
        bootstrap_admin.settings,
        "application_database_name",
        "clone_database",
    )
    assert bootstrap_admin.ensure_bootstrap_target_is_safe() == "clone_database"
