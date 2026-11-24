"""HTTP verification tests in isolated PostgreSQL schemas."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

import app.main as main_module
import app.verification_routes as verification_routes
from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from app.verification_email_crypto import decrypt_token
from app.verification_email_queue import queue_verification_email

from test_email_worker_integration import worker_database


def utc_now():
    return datetime.now(timezone.utc)


async def prepare(factory):
    key = Fernet.generate_key().decode("ascii")

    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Verification HTTP Test",
                email=f"verify-{uuid.uuid4().hex}@example.com",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()
            customer_id = customer.id

            await queue_verification_email(
                db,
                customer_id=customer_id,
                encryption_key=key,
                now=utc_now(),
            )

    async with factory() as db:
        queue = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id
                == customer_id
            )
        )
        raw_token = decrypt_token(queue.encrypted_token, key)

    return customer_id, raw_token


@pytest.fixture
def verification_http(worker_database, monkeypatch):
    monkeypatch.setattr(
        verification_routes,
        "Session",
        worker_database,
    )
    return worker_database


async def request_verify(token):
    transport = httpx.ASGITransport(
        app=main_module.app,
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.post(
            "/auth/verify-email",
            json={"token": token},
        )


def test_verification_route_registered():
    """Use public OpenAPI schema instead of FastAPI internals."""

    schema = main_module.app.openapi()
    paths = schema.get("paths", {})

    assert "/auth/verify-email" in paths

    methods = paths["/auth/verify-email"]

    assert "post" in methods


@pytest.mark.asyncio
async def test_valid_token_verifies_customer(verification_http):
    customer_id, token = await prepare(verification_http)

    response = await request_verify(token)

    assert response.status_code == 200
    assert response.json() == {
        "message": "Email verified successfully"
    }
    assert token not in response.text

    async with verification_http() as db:
        customer = await db.get(Customer, customer_id)
        record = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id
                == customer_id
            )
        )

        assert customer.email_verified_at is not None
        assert record.consumed_at is not None


@pytest.mark.asyncio
async def test_token_cannot_be_reused(verification_http):
    _, token = await prepare(verification_http)

    first = await request_verify(token)
    second = await request_verify(token)

    assert first.status_code == 200
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_expired_token_rejected(verification_http):
    customer_id, token = await prepare(verification_http)

    async with verification_http() as db:
        async with db.begin():
            record = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            record.expires_at = (
                utc_now() - timedelta(seconds=1)
            )

    response = await request_verify(token)

    assert response.status_code == 400

    async with verification_http() as db:
        customer = await db.get(Customer, customer_id)
        assert customer.email_verified_at is None


@pytest.mark.asyncio
async def test_rotated_token_rejected(verification_http):
    customer_id, token = await prepare(verification_http)

    async with verification_http() as db:
        async with db.begin():
            record = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            record.token_hash = "a" * 64

    response = await request_verify(token)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_malformed_token_rejected(verification_http):
    response = await request_verify("invalid")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_token_rejected(verification_http):
    response = await request_verify("A" * 43)

    assert response.status_code == 400
    assert "A" * 43 not in response.text
