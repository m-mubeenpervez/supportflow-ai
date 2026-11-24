"""Safety tests for first-install administrator bootstrap."""

import pytest

from scripts.bootstrap_admin import (
    PROTECTED_DATABASES,
    ensure_bootstrap_target_is_safe,
)


def test_protected_recovery_database_is_refused(monkeypatch):
    from scripts import bootstrap_admin as bootstrap

    monkeypatch.setattr(bootstrap.settings, "database_url", "postgresql+asyncpg://u:p@host/supportflow_recovery")
    monkeypatch.setattr(bootstrap.settings, "application_database_name", "supportflow_recovery")
    with pytest.raises(RuntimeError, match="protected database"):
        ensure_bootstrap_target_is_safe()


def test_test_database_is_refused(monkeypatch):
    from scripts import bootstrap_admin as bootstrap

    monkeypatch.setattr(bootstrap.settings, "database_url", "postgresql+asyncpg://u:p@host/supportflow_test_db")
    monkeypatch.setattr(bootstrap.settings, "application_database_name", "supportflow_test_db")
    with pytest.raises(RuntimeError, match="protected database"):
        ensure_bootstrap_target_is_safe()


def test_fresh_database_is_allowed(monkeypatch):
    from scripts import bootstrap_admin as bootstrap

    monkeypatch.setattr(bootstrap.settings, "database_url", "postgresql+asyncpg://u:p@host/fresh_supportflow")
    monkeypatch.setattr(bootstrap.settings, "application_database_name", "fresh_supportflow")
    assert ensure_bootstrap_target_is_safe() == "fresh_supportflow"
