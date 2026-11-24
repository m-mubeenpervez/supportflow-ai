"""HTTP-level registration tests against isolated PostgreSQL.

No application lifespan, SMTP, external HTTP requests,
or development database writes.
"""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

import app.main as main_module
import app.verification_registration as registration_module
from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)

from test_email_worker_integration import worker_database


def new_email():
    return f"http-register-{uuid.uuid4().hex}@gmail.com"


def registration_data(email=None):
    return {
        "name": "HTTP Registration Test",
        "email": email or new_email(),
        "password": "TestPassword123!",
    }


async def counts(factory):
    async with factory() as db:
        result = []

        for model in (
            Customer,
            EmailVerificationToken,
            VerificationEmailOutbox,
        ):
            result.append(
                await db.scalar(
                    select(func.count()).select_from(model)
                )
            )

        return tuple(result)


@pytest.fixture
def isolated_http_registration(worker_database, monkeypatch):
    """Redirect registration to the isolated test schema."""

    key = Fernet.generate_key().decode("ascii")

    monkeypatch.setattr(
        main_module,
        "Session",
        worker_database,
    )

    monkeypatch.setattr(
        main_module,
        "get_verification_email_config",
        lambda: SimpleNamespace(
            encryption_key=key,
            base_url="http://localhost:5173/verify-email",
        ),
    )

    return worker_database


def test_registration_route_exists():
    routes = [
        route
        for route in main_module.app.routes
        if getattr(route, "path", None) == "/auth/register"
        and "POST" in getattr(route, "methods", set())
    ]

    assert len(routes) == 1


@pytest.mark.asyncio
async def test_http_registration_creates_atomic_queue(
    isolated_http_registration,
):
    factory = isolated_http_registration
    email = new_email()
    data = registration_data(email.upper())

    transport = httpx.ASGITransport(
        app=main_module.app,
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/auth/register",
            json=data,
        )

    assert response.status_code in {200, 201}, response.text

    body = response.json()

    assert body["email"] == email
    assert body["name"] == data["name"]
    assert isinstance(body["id"], int)
    assert set(body) == {"id", "name", "email"}
    assert "token" not in response.text.lower()
    assert "password" not in response.text.lower()

    assert await counts(factory) == (1, 1, 1)

    async with factory() as db:
        customer = await db.get(Customer, body["id"])

        token = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id
                == body["id"]
            )
        )

        queue = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id
                == body["id"]
            )
        )

        assert customer.email_verified_at is None
        assert token.token_hash == queue.token_hash
        assert queue.status == "pending"
        assert queue.attempts == 0


@pytest.mark.asyncio
async def test_missing_configuration_returns_503(
    isolated_http_registration,
    monkeypatch,
):
    factory = isolated_http_registration

    def missing_config():
        raise RuntimeError("SECRET CONFIGURATION DETAILS")

    monkeypatch.setattr(
        main_module,
        "get_verification_email_config",
        missing_config,
    )

    transport = httpx.ASGITransport(
        app=main_module.app,
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/auth/register",
            json=registration_data(),
        )

    assert response.status_code == 503
    assert "SECRET CONFIGURATION DETAILS" not in response.text
    assert await counts(factory) == (0, 0, 0)


@pytest.mark.asyncio
async def test_duplicate_email_returns_409(
    isolated_http_registration,
):
    factory = isolated_http_registration
    data = registration_data()

    transport = httpx.ASGITransport(
        app=main_module.app,
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/auth/register",
            json=data,
        )
        second = await client.post(
            "/auth/register",
            json=data,
        )

    assert first.status_code in {200, 201}
    assert second.status_code == 409
    assert second.json()["detail"] == "Email already registered"
    assert await counts(factory) == (1, 1, 1)


@pytest.mark.asyncio
async def test_queue_failure_rolls_back_http_registration(
    isolated_http_registration,
    monkeypatch,
):
    factory = isolated_http_registration

    async def broken_queue(*args, **kwargs):
        raise RuntimeError("FAKE PRIVATE QUEUE FAILURE")

    monkeypatch.setattr(
        registration_module,
        "queue_verification_email",
        broken_queue,
    )

    transport = httpx.ASGITransport(
        app=main_module.app,
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/auth/register",
            json=registration_data(),
        )

    assert response.status_code == 500
    assert "FAKE PRIVATE QUEUE FAILURE" not in response.text
    assert await counts(factory) == (0, 0, 0)


@pytest.mark.asyncio
async def test_invalid_email_returns_422(
    isolated_http_registration,
):
    factory = isolated_http_registration

    data = registration_data()
    data["email"] = "not-an-email"

    transport = httpx.ASGITransport(
        app=main_module.app,
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/auth/register",
            json=data,
        )

    assert response.status_code == 422
    assert await counts(factory) == (0, 0, 0)
