"""PostgreSQL integration tests for email verification.

Uses an isolated temporary schema and never sends email.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.email_verification_service import (
    AlreadyVerifiedError,
    VerificationCooldownError,
    consume_verification_token,
    issue_verification_token,
)
from app.models import Customer, EmailVerificationToken

# Reuse the previously verified isolated test-schema fixture.
from test_email_worker_integration import worker_database


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


async def create_customer(factory):
    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Verification Integration Test",
                email=f"verify-{uuid.uuid4().hex}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()
            customer_id = customer.id

    return customer_id


async def issue(factory, customer_id, now=NOW):
    async with factory() as db:
        async with db.begin():
            return await issue_verification_token(
                db,
                customer_id=customer_id,
                now=now,
            )


async def consume(factory, token, now=NOW):
    async with factory() as db:
        async with db.begin():
            return await consume_verification_token(
                db,
                raw_token=token,
                now=now,
            )


async def read_state(factory, customer_id):
    async with factory() as db:
        customer = await db.get(Customer, customer_id)
        record = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id
                == customer_id
            )
        )

        return customer, record


@pytest.mark.asyncio
async def test_issue_stores_hash_not_raw_token(worker_database):
    customer_id = await create_customer(worker_database)
    challenge = await issue(worker_database, customer_id)

    customer, record = await read_state(
        worker_database, customer_id
    )

    assert record is not None
    assert record.token_hash == challenge.token_hash
    assert record.token_hash != challenge.raw_token
    assert len(record.token_hash) == 64
    assert record.expires_at == NOW + timedelta(minutes=30)
    assert record.consumed_at is None
    assert customer.email_verified_at is None


@pytest.mark.asyncio
async def test_resend_cooldown_blocks_early_request(worker_database):
    customer_id = await create_customer(worker_database)
    first = await issue(worker_database, customer_id)

    with pytest.raises(VerificationCooldownError):
        await issue(
            worker_database,
            customer_id,
            now=NOW + timedelta(seconds=59),
        )

    _, record = await read_state(worker_database, customer_id)
    assert record.token_hash == first.token_hash


@pytest.mark.asyncio
async def test_resend_rotates_and_invalidates_old_token(
    worker_database,
):
    customer_id = await create_customer(worker_database)
    first = await issue(worker_database, customer_id)

    second = await issue(
        worker_database,
        customer_id,
        now=NOW + timedelta(seconds=60),
    )

    assert first.token_hash != second.token_hash

    assert not await consume(
        worker_database,
        first.raw_token,
        now=NOW + timedelta(seconds=61),
    )

    assert await consume(
        worker_database,
        second.raw_token,
        now=NOW + timedelta(seconds=61),
    )


@pytest.mark.asyncio
async def test_expired_token_cannot_verify_customer(worker_database):
    customer_id = await create_customer(worker_database)
    challenge = await issue(worker_database, customer_id)

    assert not await consume(
        worker_database,
        challenge.raw_token,
        now=NOW + timedelta(minutes=30),
    )

    customer, record = await read_state(
        worker_database, customer_id
    )

    assert customer.email_verified_at is None
    assert record.consumed_at is None


@pytest.mark.asyncio
async def test_valid_token_is_one_time_only(worker_database):
    customer_id = await create_customer(worker_database)
    challenge = await issue(worker_database, customer_id)

    verification_time = NOW + timedelta(minutes=1)

    assert await consume(
        worker_database,
        challenge.raw_token,
        now=verification_time,
    )

    assert not await consume(
        worker_database,
        challenge.raw_token,
        now=verification_time + timedelta(seconds=1),
    )

    customer, record = await read_state(
        worker_database, customer_id
    )

    assert customer.email_verified_at == verification_time
    assert record.consumed_at == verification_time


@pytest.mark.asyncio
async def test_concurrent_consumption_allows_one_success(
    worker_database,
):
    customer_id = await create_customer(worker_database)
    challenge = await issue(worker_database, customer_id)

    results = await asyncio.gather(
        consume(
            worker_database,
            challenge.raw_token,
            now=NOW + timedelta(minutes=1),
        ),
        consume(
            worker_database,
            challenge.raw_token,
            now=NOW + timedelta(minutes=1),
        ),
    )

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_verified_customer_cannot_request_new_token(
    worker_database,
):
    customer_id = await create_customer(worker_database)
    challenge = await issue(worker_database, customer_id)

    assert await consume(
        worker_database,
        challenge.raw_token,
        now=NOW + timedelta(minutes=1),
    )

    with pytest.raises(AlreadyVerifiedError):
        await issue(
            worker_database,
            customer_id,
            now=NOW + timedelta(minutes=2),
        )


@pytest.mark.asyncio
async def test_unknown_customer_cannot_issue_token(worker_database):
    with pytest.raises(
        ValueError,
        match="Customer does not exist",
    ):
        await issue(
            worker_database,
            customer_id=2147483647,
        )
