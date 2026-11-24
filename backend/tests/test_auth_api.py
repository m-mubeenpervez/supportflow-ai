
"""Authentication API tests using isolated PostgreSQL."""

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.auth import decode_access_token
from test_email_worker_integration import worker_database


@pytest.mark.asyncio
async def test_registration_and_login_api(
    monkeypatch,
    worker_database,
):
    # Use the isolated PostgreSQL test session.
    monkeypatch.setattr(
        main,
        "Session",
        worker_database,
    )

    # Mock verification configuration for isolated HTTP testing.
    # No live SMTP credentials or actual delivery are used.
    from types import SimpleNamespace
    from cryptography.fernet import Fernet

    verification_key = Fernet.generate_key().decode("ascii")

    monkeypatch.setattr(
        main,
        "get_verification_email_config",
        lambda: SimpleNamespace(
            encryption_key=verification_key,
            base_url="http://localhost:5173/verify-email",
        ),
    )

    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:

        registration = {
            "name": "Test Customer",
            "email": "customer@example.com",
            "password": "SecurePassword123!",
        }

        # 1. Successful registration
        response = await client.post(
            "/auth/register",
            json=registration,
        )

        assert response.status_code == 201

        customer = response.json()

        assert customer["email"] == registration["email"]
        assert "password_hash" not in customer

        # 2. Duplicate email rejected
        response = await client.post(
            "/auth/register",
            json=registration,
        )

        assert response.status_code == 409

        # 3. Successful login
        response = await client.post(
            "/auth/login",
            json={
                "email": registration["email"],
                "password": registration["password"],
            },
        )

        assert response.status_code == 200

        token_data = response.json()

        assert token_data["token_type"] == "bearer"

        customer_id = decode_access_token(
            token_data["access_token"]
        )

        assert customer_id == customer["id"]

        # 4. Wrong password rejected
        response = await client.post(
            "/auth/login",
            json={
                "email": registration["email"],
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code == 401

        # 5. Invalid email rejected
        response = await client.post(
            "/auth/register",
            json={
                "name": "Invalid Email",
                "email": "not-an-email",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 422
