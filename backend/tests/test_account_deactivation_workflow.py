
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app import main as main_module
from app.auth import hash_password
from app.main import app, require_verified_customer


TEST_PASSWORD = "SyntheticAccountPassword1!"
TEST_ID = 987654321


class FakeSession:
    def __init__(self, account):
        self.account = account
        self.pending_ticket = False
        self.pending_emails = 0
        self.transaction_completed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return FakeTransaction(self)

    async def scalar(self, statement, params=None):
        sql = str(statement).lower()

        if "from customers" in sql:
            return self.account

        if "from tickets" in sql:
            return 123 if self.pending_ticket else None

        if "from public.email_outbox" in sql:
            return self.pending_emails

        raise AssertionError("Unexpected database query")


class FakeTransaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.session.transaction_completed = True
        return False


@pytest.fixture
def environment(monkeypatch):
    account = SimpleNamespace(
        id=TEST_ID,
        password_hash=hash_password(TEST_PASSWORD),
        deactivated_at=None,
    )

    session = FakeSession(account)

    monkeypatch.setattr(
        main_module,
        "Session",
        lambda: session,
    )

    app.dependency_overrides[require_verified_customer] = (
        lambda: SimpleNamespace(id=TEST_ID)
    )

    yield account, session

    app.dependency_overrides.pop(
        require_verified_customer,
        None,
    )


def request_deactivation(password=TEST_PASSWORD, confirmation="DEACTIVATE"):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/auth/deactivate-account",
                json={
                    "password": password,
                    "confirmation": confirmation,
                },
            )

    return asyncio.run(send())


def test_successful_deactivation(environment):
    account, session = environment

    result = request_deactivation()

    assert result.status_code == 200
    assert result.json()["deactivated"] is True
    assert account.deactivated_at is not None
    assert session.transaction_completed


def test_wrong_password_rejected(environment):
    account, session = environment

    result = request_deactivation(
        password="IncorrectSyntheticPassword1!"
    )

    assert result.status_code == 403
    assert account.deactivated_at is None
    assert not session.transaction_completed


def test_missing_confirmation_rejected(environment):
    account, session = environment

    result = request_deactivation(confirmation="DELETE")

    assert result.status_code == 400
    assert account.deactivated_at is None
    assert not session.transaction_completed


def test_pending_approval_blocks_deactivation(environment):
    account, session = environment
    session.pending_ticket = True

    result = request_deactivation()

    assert result.status_code == 409
    assert account.deactivated_at is None
    assert not session.transaction_completed


def test_pending_email_blocks_deactivation(environment):
    account, session = environment
    session.pending_emails = 1

    result = request_deactivation()

    assert result.status_code == 409
    assert account.deactivated_at is None
    assert not session.transaction_completed


def test_already_deactivated_account_rejected(environment):
    account, session = environment
    account.deactivated_at = datetime.now(timezone.utc)

    result = request_deactivation()

    assert result.status_code == 401
    assert not session.transaction_completed
