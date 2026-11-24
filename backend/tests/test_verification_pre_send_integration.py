"""Isolated PostgreSQL tests for pre-send claim validation."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from app.verification_email_queue import queue_verification_email
from app.verification_email_worker import claim_verification_email
from app.verification_pre_send import validate_claim_before_send

from test_email_worker_integration import worker_database


def utc_now():
    return datetime.now(timezone.utc)


async def prepare(factory):
    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Pre Send Test",
                email=f"presend-{uuid.uuid4().hex}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()
            customer_id = customer.id

            await queue_verification_email(
                db,
                customer_id=customer_id,
                encryption_key=Fernet.generate_key().decode("ascii"),
                now=utc_now(),
            )

    job = await claim_verification_email(
        session_factory=factory,
        allow_mock_delivery=True,
    )
    assert job is not None
    return customer_id, job


@pytest.mark.asyncio
async def test_valid_claim_passes(worker_database):
    _, job = await prepare(worker_database)

    result = await validate_claim_before_send(
        job, worker_database
    )

    assert result.allowed
    assert result.reason == "eligible"


@pytest.mark.asyncio
async def test_stale_claim_is_rejected(worker_database):
    _, job = await prepare(worker_database)

    stale_job = replace(
        job, claim_token=str(uuid.uuid4())
    )

    result = await validate_claim_before_send(
        stale_job, worker_database
    )

    assert not result.allowed
    assert result.reason == "claim_mismatch"


@pytest.mark.asyncio
async def test_verified_customer_rejected(worker_database):
    customer_id, job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            customer = await db.get(Customer, customer_id)
            customer.email_verified_at = utc_now()

    result = await validate_claim_before_send(
        job, worker_database
    )

    assert not result.allowed
    assert result.reason == "already_verified"


@pytest.mark.asyncio
async def test_rotated_token_rejected(worker_database):
    customer_id, job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            token = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            token.token_hash = "a" * 64

    result = await validate_claim_before_send(
        job, worker_database
    )

    assert not result.allowed
    assert result.reason == "token_rotated"


@pytest.mark.asyncio
async def test_expired_lease_rejected(worker_database):
    customer_id, job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            outbox = await db.scalar(
                select(VerificationEmailOutbox).where(
                    VerificationEmailOutbox.customer_id
                    == customer_id
                )
            )
            outbox.lease_expires_at = (
                utc_now() - timedelta(seconds=1)
            )

    result = await validate_claim_before_send(
        job, worker_database
    )

    assert not result.allowed
    assert result.reason == "lease_expired"


@pytest.mark.asyncio
async def test_replaced_payload_rejected(worker_database):
    customer_id, job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            outbox = await db.scalar(
                select(VerificationEmailOutbox).where(
                    VerificationEmailOutbox.customer_id
                    == customer_id
                )
            )
            outbox.encrypted_token = "replaced-payload"

    result = await validate_claim_before_send(
        job, worker_database
    )

    assert not result.allowed
    assert result.reason == "payload_replaced"


@pytest.mark.asyncio
async def test_consumed_token_rejected(worker_database):
    customer_id, job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            token = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            token.consumed_at = utc_now()

    result = await validate_claim_before_send(
        job, worker_database
    )

    assert not result.allowed
    assert result.reason == "token_inactive"
