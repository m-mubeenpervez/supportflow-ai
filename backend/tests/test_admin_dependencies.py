"""Unit tests for database-backed administrator authorization."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import admin_dependencies as dependencies
from app.admin_auth import create_admin_access_token
from app.auth import create_access_token
from app.config import settings


@pytest.fixture(autouse=True)
def isolated_secret(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        "isolated-admin-dependency-test-secret",
    )


class FakeSession:
    def __init__(self, account):
        self.account = account

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, identity):
        if identity != 7:
            return None
        return self.account


def account(**changes):
    values = dict(
        id=7,
        is_active=True,
        password_hash="synthetic-test-hash",
        role="admin",
        session_version=2,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def setup(monkeypatch, record):
    monkeypatch.setattr(
        dependencies,
        "Session",
        lambda: FakeSession(record),
    )


def credentials(token):
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )


@pytest.mark.asyncio
async def test_valid_admin_accepted(monkeypatch):
    setup(monkeypatch, account())
    result = await dependencies.get_current_admin(
        credentials(create_admin_access_token(7, 2))
    )
    assert result.id == 7


@pytest.mark.asyncio
async def test_missing_admin_token_rejected():
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_customer_token_rejected():
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(
            credentials(create_access_token(7, 2))
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_disabled_admin_rejected(monkeypatch):
    setup(monkeypatch, account(is_active=False))
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(
            credentials(create_admin_access_token(7, 2))
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_revoked_session_rejected(monkeypatch):
    setup(monkeypatch, account(session_version=3))
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(
            credentials(create_admin_access_token(7, 2))
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_admin_account_rejected(monkeypatch):
    setup(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(
            credentials(create_admin_access_token(7, 2))
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_role_rejected(monkeypatch):
    setup(monkeypatch, account(role="customer"))
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(
            credentials(create_admin_access_token(7, 2))
        )
    assert exc.value.status_code == 401


def test_regular_admin_cannot_use_super_admin_permissions():
    with pytest.raises(HTTPException) as exc:
        dependencies.require_super_admin(account())
    assert exc.value.status_code == 403


def test_super_admin_permissions_accepted():
    record = account(role="super_admin")
    result = dependencies.require_super_admin(record)
    assert result is record


@pytest.mark.asyncio
async def test_missing_password_hash_rejected(monkeypatch):
    setup(monkeypatch, account(password_hash=""))
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_admin(
            credentials(create_admin_access_token(7, 2))
        )
    assert exc.value.status_code == 401
