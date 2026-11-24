
import asyncio
from types import SimpleNamespace

import httpx
import pytest

import app.main as main_module
from app.auth import hash_password, verify_password
from app.main import app, require_verified_customer


OLD_PASSWORD = "OriginalSecurePassword1!"
NEW_PASSWORD = "UpdatedSecurePassword2@"


class FakeSession:
    def __init__(self, account):
        self.account = account
        self.commit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return self

    async def scalar(self, statement):
        return self.account


@pytest.fixture
def account_environment(monkeypatch):
    account = SimpleNamespace(
        id=987654321,
        password_hash=hash_password(OLD_PASSWORD),
        deactivated_at=None,
        session_version=0,
    )

    session = FakeSession(account)

    monkeypatch.setattr(
        main_module,
        "Session",
        lambda: session,
    )

    app.dependency_overrides[require_verified_customer] = (
        lambda: SimpleNamespace(id=account.id)
    )

    yield account

    app.dependency_overrides.pop(
        require_verified_customer,
        None,
    )


def request_password_change(current, new, confirm):
    async def send():
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/auth/change-password",
                json={
                    "current_password": current,
                    "new_password": new,
                    "confirm_password": confirm,
                },
            )

    return asyncio.run(send())


def test_wrong_current_password_rejected(account_environment):
    account = account_environment
    original_hash = account.password_hash

    response = request_password_change(
        "IncorrectPassword1!",
        NEW_PASSWORD,
        NEW_PASSWORD,
    )

    assert response.status_code == 403
    assert account.password_hash == original_hash
    assert account.session_version == 0


def test_cannot_reuse_current_password(account_environment):
    account = account_environment

    response = request_password_change(
        OLD_PASSWORD,
        OLD_PASSWORD,
        OLD_PASSWORD,
    )

    assert response.status_code == 400
    assert account.session_version == 0
    assert verify_password(
        OLD_PASSWORD,
        account.password_hash,
    )


def test_successful_change_hashes_password(account_environment):
    account = account_environment
    original_hash = account.password_hash

    response = request_password_change(
        OLD_PASSWORD,
        NEW_PASSWORD,
        NEW_PASSWORD,
    )

    assert response.status_code == 200
    assert response.json()["password_changed"] is True

    assert account.password_hash != original_hash
    assert verify_password(
        NEW_PASSWORD,
        account.password_hash,
    )
    assert not verify_password(
        OLD_PASSWORD,
        account.password_hash,
    )
    assert account.session_version == 1


def test_failed_change_keeps_original_password(account_environment):
    account = account_environment
    original_hash = account.password_hash

    response = request_password_change(
        OLD_PASSWORD,
        "weakpassword",
        "weakpassword",
    )

    assert response.status_code == 400
    assert account.password_hash == original_hash
    assert account.session_version == 0
