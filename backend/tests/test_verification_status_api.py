"""Authenticated email verification status API tests."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app import main


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verified,expected",
    [
        (False, False),
        (True, True),
    ],
)
async def test_verification_status(verified, expected):
    customer = SimpleNamespace(
        id=123,
        email_verified_at=(
            datetime.now(timezone.utc) if verified else None
        ),
    )

    async def fake_customer():
        return customer

    main.app.dependency_overrides[
        main.get_current_customer
    ] = fake_customer

    try:
        transport = ASGITransport(app=main.app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/auth/verification-status"
            )

        assert response.status_code == 200
        assert response.json() == {
            "email_verified": expected
        }
        assert response.headers["cache-control"] == "no-store"
    finally:
        main.app.dependency_overrides.pop(
            main.get_current_customer,
            None,
        )


@pytest.mark.asyncio
async def test_verification_status_requires_authentication():
    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/auth/verification-status"
        )

    assert response.status_code == 401
