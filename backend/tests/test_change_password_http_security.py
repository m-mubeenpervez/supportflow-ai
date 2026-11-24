
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.main import app, require_verified_customer


VALID = {
    "current_password": "CurrentTestPassword1!",
    "new_password": "NewSecurePassword9@",
    "confirm_password": "NewSecurePassword9@",
}


async def post_password(payload, headers=None):
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.post(
            "/auth/change-password",
            json=payload,
            headers=headers or {},
        )


@pytest.fixture
def mock_verified_customer():
    # Synthetic customer. No database writes or real JWT required.
    app.dependency_overrides[require_verified_customer] = (
        lambda: SimpleNamespace(id=999999)
    )

    yield

    app.dependency_overrides.pop(
        require_verified_customer,
        None,
    )


def test_rejects_weak_password(mock_verified_customer):
    payload = {
        **VALID,
        "new_password": "weakpassword",
        "confirm_password": "weakpassword",
    }

    response = asyncio.run(post_password(payload))

    assert response.status_code == 400
    assert "required" in response.json()["detail"].lower()


def test_rejects_mismatched_passwords(mock_verified_customer):
    payload = {
        **VALID,
        "confirm_password": "DifferentSecurePassword7!",
    }

    response = asyncio.run(post_password(payload))

    assert response.status_code == 400
    assert "match" in response.json()["detail"].lower()


def test_rejects_missing_current_password(mock_verified_customer):
    payload = {
        "new_password": VALID["new_password"],
        "confirm_password": VALID["confirm_password"],
    }

    response = asyncio.run(post_password(payload))

    assert response.status_code == 422


def test_rejects_invalid_jwt():
    response = asyncio.run(
        post_password(
            VALID,
            headers={"Authorization": "Bearer invalid-jwt"},
        )
    )

    assert response.status_code == 401


def test_rejects_missing_authentication():
    response = asyncio.run(post_password(VALID))

    assert response.status_code in (401, 403)
