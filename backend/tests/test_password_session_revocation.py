
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app import main as main_module
from app.auth import create_access_token


CUSTOMER_ID = 98765432


class FakeSession:
    def __init__(self, customer):
        self.customer = customer

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, customer_id):
        if customer_id == self.customer.id:
            return self.customer
        return None


@pytest.fixture
def customer_environment(monkeypatch):
    customer = SimpleNamespace(
        id=CUSTOMER_ID,
        email="synthetic-customer@example.invalid",
        name="Synthetic Customer",
        password_hash="synthetic-hash-not-a-real-password",
        email_verified_at=datetime.now(timezone.utc),
        deactivated_at=None,
        session_version=0,
    )

    monkeypatch.setattr(
        main_module,
        "Session",
        lambda: FakeSession(customer),
    )

    yield customer


def request_profile(token=None):
    async def send():
        transport = httpx.ASGITransport(
            app=main_module.app,
        )

        headers = {}

        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/auth/me",
                headers=headers,
            )

    return asyncio.run(send())


def test_current_session_can_access_profile(customer_environment):
    token = create_access_token(CUSTOMER_ID, 0)

    response = request_profile(token)

    assert response.status_code == 200
    assert response.json()["id"] == CUSTOMER_ID


def test_old_jwt_rejected_after_password_version_changes(
    customer_environment,
):
    old_token = create_access_token(CUSTOMER_ID, 0)

    customer_environment.session_version = 1

    response = request_profile(old_token)

    assert response.status_code == 401


def test_new_version_jwt_accepted(customer_environment):
    customer_environment.session_version = 1

    new_token = create_access_token(CUSTOMER_ID, 1)

    response = request_profile(new_token)

    assert response.status_code == 200


def test_deactivated_account_rejected(customer_environment):
    customer_environment.deactivated_at = datetime.now(
        timezone.utc
    )

    token = create_access_token(CUSTOMER_ID, 0)

    response = request_profile(token)

    assert response.status_code == 401


def test_unverified_account_rejected(customer_environment):
    customer_environment.email_verified_at = None

    token = create_access_token(CUSTOMER_ID, 0)

    response = request_profile(token)

    assert response.status_code == 403


def test_token_for_different_customer_rejected(
    customer_environment,
):
    other_token = create_access_token(CUSTOMER_ID + 1, 0)

    response = request_profile(other_token)

    assert response.status_code == 401


def test_missing_token_rejected(customer_environment):
    response = request_profile()

    assert response.status_code == 401


def test_invalid_token_rejected(customer_environment):
    response = request_profile("invalid-jwt")

    assert response.status_code == 401
