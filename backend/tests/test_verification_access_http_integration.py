"""Real JWT and isolated PostgreSQL email verification access test."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.auth import create_access_token
from app.models import Customer


@pytest.mark.asyncio
async def test_real_jwt_verification_access_flow(
    monkeypatch,
    postgres_session,
):
    # Reuse the existing isolated PostgreSQL test fixture.
    monkeypatch.setattr(main, "Session", postgres_session)

    async with postgres_session() as db:
        customer = Customer(
            name="Verification Access Integration Customer",
            email=f"verification-access-{uuid4().hex}@test.local",
            password_hash="TEST_ONLY",
            email_verified_at=None,
        )

        db.add(customer)
        await db.flush()
        customer_id = customer.id
        await db.commit()

    token = create_access_token(customer_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:

        # Missing and invalid authentication must be rejected.
        response = await client.get(
            "/auth/verification-status"
        )
        assert response.status_code == 401

        response = await client.get(
            "/auth/verification-status",
            headers={"Authorization": "Bearer invalid.jwt"},
        )
        assert response.status_code == 401

        # A valid JWT alone does not imply verified email.
        response = await client.get(
            "/auth/verification-status",
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json() == {"email_verified": False}
        assert response.headers["cache-control"] == "no-store"

        protected_requests = [
            ("GET", "/customer/tickets"),
            ("GET", "/notifications/customer"),
            ("POST", "/chat"),
        ]

        for method, endpoint in protected_requests:
            kwargs = {"headers": headers}
            if endpoint == "/chat":
                kwargs["json"] = {
                    "message": "This must not reach the AI graph"
                }

            response = await client.request(
                method,
                endpoint,
                **kwargs,
            )

            assert response.status_code == 403, (
                endpoint,
                response.text,
            )
            assert response.json()["detail"] == (
                "Email verification required"
            )

        # Simulate successful verification by changing only
        # this customer's record in the isolated test database.
        async with postgres_session() as db:
            saved = await db.get(Customer, customer_id)
            assert saved is not None
            saved.email_verified_at = datetime.now(timezone.utc)
            await db.commit()

        # Same valid JWT now belongs to a verified customer.
        response = await client.get(
            "/auth/verification-status",
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json() == {"email_verified": True}
        assert response.headers["cache-control"] == "no-store"

        # Verified customers can access protected read endpoints.
        for endpoint in (
            "/customer/tickets",
            "/notifications/customer",
        ):
            response = await client.get(
                endpoint,
                headers=headers,
            )

            assert response.status_code == 200, (
                endpoint,
                response.text,
            )

    print("Missing/invalid JWT: BLOCKED")
    print("Unverified status: FALSE")
    print("Unverified protected requests: BLOCKED")
    print("Verified status: TRUE")
    print("Verified customer read endpoints: ALLOWED")
