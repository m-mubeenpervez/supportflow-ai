"""Isolated PostgreSQL tests for verification worker claims.

Uses the existing worker_database temporary-schema fixture.
No real SMTP delivery or development database modifications.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from app.verification_email_queue import queue_verification_email
from app.verification_email_worker import (
    claim_verification_email,
)

from test_email_worker_integration import worker_database


def current_time():
    return datetime.now(timezone.utc)


def encryption_key():
    return Fernet.generate_key().decode("ascii")


async def create_queued_customer(factory):
    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Verification Claim Test",
                email=f"claim-{uuid.uuid4().hex}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()
            customer_id = customer.id

            await queue_verification_email(
                db,
                customer_id=customer_id,
                encryption_key=encryption_key(),
                now=current_time(),
            )

    return customer_id


async def read_outbox(factory, customer_id):
    async with factory() as db:
        return await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id
                == customer_id
            )
        )


async def mock_claim(factory):
    return await claim_verification_email(
        session_factory=factory,
        allow_mock_delivery=True,
    )


@pytest.mark.asyncio
async def test_disabled_worker_does_not_claim(worker_database):
    customer_id = await create_queued_customer(worker_database)

    assert settings.email_delivery_enabled is False

    result = await claim_verification_email(
        session_factory=worker_database,
    )

    assert result is None

    outbox = await read_outbox(worker_database, customer_id)
    assert outbox.status == "pending"
    assert outbox.attempts == 0


@pytest.mark.asyncio
async def test_valid_email_claim_sets_lease(worker_database):
    customer_id = await create_queued_customer(worker_database)

    job = await mock_claim(worker_database)

    assert job is not None
    assert job.customer_id == customer_id
    assert job.attempts == 1
    assert job.claim_token
    assert job.lease_expires_at > current_time()

    outbox = await read_outbox(worker_database, customer_id)
    assert outbox.status == "processing"
    assert outbox.claim_token == job.claim_token


@pytest.mark.asyncio
async def test_second_claim_cannot_reclaim_active_job(
    worker_database,
):
    await create_queued_customer(worker_database)

    first = await mock_claim(worker_database)
    second = await mock_claim(worker_database)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_concurrent_workers_claim_only_once(worker_database):
    await create_queued_customer(worker_database)

    results = await asyncio.wait_for(
        asyncio.gather(
            mock_claim(worker_database),
            mock_claim(worker_database),
        ),
        timeout=20,
    )

    assert sum(job is not None for job in results) == 1


@pytest.mark.asyncio
async def test_expired_token_cannot_be_claimed(worker_database):
    customer_id = await create_queued_customer(worker_database)

    async with worker_database() as db:
        async with db.begin():
            token = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            token.expires_at = (
                current_time() - timedelta(seconds=1)
            )

    assert await mock_claim(worker_database) is None


@pytest.mark.asyncio
async def test_consumed_token_cannot_be_claimed(worker_database):
    customer_id = await create_queued_customer(worker_database)

    async with worker_database() as db:
        async with db.begin():
            token = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            token.consumed_at = current_time()

    assert await mock_claim(worker_database) is None


@pytest.mark.asyncio
async def test_rotated_token_cannot_be_claimed(worker_database):
    customer_id = await create_queued_customer(worker_database)

    async with worker_database() as db:
        async with db.begin():
            token = await db.scalar(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.customer_id
                    == customer_id
                )
            )
            token.token_hash = "a" * 64

    assert await mock_claim(worker_database) is None


@pytest.mark.asyncio
async def test_verified_customer_cannot_be_claimed(worker_database):
    customer_id = await create_queued_customer(worker_database)

    async with worker_database() as db:
        async with db.begin():
            customer = await db.get(Customer, customer_id)
            customer.email_verified_at = current_time()

    assert await mock_claim(worker_database) is None


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed(worker_database):
    customer_id = await create_queued_customer(worker_database)

    first = await mock_claim(worker_database)
    assert first is not None

    async with worker_database() as db:
        async with db.begin():
            outbox = await db.scalar(
                select(VerificationEmailOutbox).where(
                    VerificationEmailOutbox.customer_id
                    == customer_id
                )
            )
            outbox.lease_expires_at = (
                current_time() - timedelta(seconds=1)
            )

    second = await mock_claim(worker_database)

    assert second is not None
    assert second.id == first.id
    assert second.claim_token != first.claim_token
    assert second.attempts == 2


@pytest.mark.asyncio
async def test_retry_limit_prevents_claim(worker_database):
    customer_id = await create_queued_customer(worker_database)

    async with worker_database() as db:
        async with db.begin():
            outbox = await db.scalar(
                select(VerificationEmailOutbox).where(
                    VerificationEmailOutbox.customer_id
                    == customer_id
                )
            )
            outbox.attempts = settings.email_max_attempts

    assert await mock_claim(worker_database) is None
