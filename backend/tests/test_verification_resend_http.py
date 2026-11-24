"""Authenticated resend HTTP tests, isolated PostgreSQL only."""

from datetime import datetime, timedelta, timezone
import uuid
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

import app.main as main_module
from app.email_verification_service import consume_verification_token
from app.models import Customer, EmailVerificationToken, VerificationEmailOutbox
from app.verification_email_queue import queue_verification_email
from app.verification_email_crypto import decrypt_token
from app.email_verification import hash_token
from test_email_worker_integration import worker_database


@pytest.fixture
def context(worker_database, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(main_module, "Session", worker_database)
    monkeypatch.setattr(
        main_module, "get_verification_email_config",
        lambda: SimpleNamespace(
            encryption_key=key,
            base_url="http://localhost:5173/verify-email",
        ),
    )
    return worker_database, key


async def create_customer(factory, key):
    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Resend Test",
                email=f"resend-{uuid.uuid4().hex}@gmail.com",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()
            customer_id = customer.id
            await queue_verification_email(
                db, customer_id=customer_id,
                encryption_key=key,
            )
    return customer_id


async def request(token=None):
    transport = httpx.ASGITransport(
        app=main_module.app, raise_app_exceptions=False
    )
    headers = (
        {"Authorization": f"Bearer {token}"}
        if token else {}
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.post(
            "/auth/resend-verification", headers=headers
        )


def test_resend_route_in_openapi():
    assert "post" in main_module.app.openapi()["paths"][
        "/auth/resend-verification"
    ]


@pytest.mark.asyncio
async def test_anonymous_resend_rejected(context):
    response = await request()
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_immediate_resend_rate_limited(context):
    factory, key = context
    customer_id = await create_customer(factory, key)
    token = main_module.create_access_token(customer_id)
    response = await request(token)
    assert response.status_code == 429
    assert "token" not in response.text.lower()


@pytest.mark.asyncio
async def test_resend_rotates_token_and_queue(context):
    factory, key = context
    customer_id = await create_customer(factory, key)

    async with factory() as db:
        async with db.begin():
            record = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id == customer_id
                )
            )
            previous_hash = record.token_hash
            record.last_sent_at = (
                datetime.now(timezone.utc) - timedelta(seconds=65)
            )

    token = main_module.create_access_token(customer_id)
    response = await request(token)

    assert response.status_code == 202, response.text
    assert response.json() == {
        "message": "Verification email queued"
    }

    async with factory() as db:
        record = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id == customer_id
            )
        )
        queue = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id == customer_id
            )
        )
        assert record.token_hash != previous_hash
        assert record.token_hash == queue.token_hash
        assert queue.status == "pending"
        assert queue.attempts == 0
        raw = decrypt_token(queue.encrypted_token, key)
        assert hash_token(raw) == record.token_hash
        assert raw not in response.text


@pytest.mark.asyncio
async def test_verified_customer_rejected(context):
    factory, key = context
    customer_id = await create_customer(factory, key)

    async with factory() as db:
        async with db.begin():
            customer = await db.get(Customer, customer_id)
            customer.email_verified_at = datetime.now(timezone.utc)

    token = main_module.create_access_token(customer_id)
    response = await request(token)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_missing_config_returns_503(context, monkeypatch):
    factory, key = context
    customer_id = await create_customer(factory, key)

    def missing():
        raise RuntimeError("private config details")

    monkeypatch.setattr(
        main_module, "get_verification_email_config", missing
    )

    token = main_module.create_access_token(customer_id)
    response = await request(token)
    assert response.status_code == 503
    assert "private config details" not in response.text
