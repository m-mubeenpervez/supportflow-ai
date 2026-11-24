"""Isolated PostgreSQL integration tests for verification queue.

No development database writes, SMTP calls, or external APIs.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.email_verification import hash_token
from app.email_verification_service import (
    AlreadyVerifiedError,
    VerificationCooldownError,
    consume_verification_token,
)
from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from app.verification_email_crypto import decrypt_token
from app.verification_email_queue import queue_verification_email

from test_email_worker_integration import worker_database


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def new_key():
    return Fernet.generate_key().decode("ascii")


async def create_customer(factory):
    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Queue Integration Test",
                email=f"queue-{uuid.uuid4().hex}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()
            return customer.id


async def queue(factory, customer_id, key, now=NOW):
    async with factory() as db:
        async with db.begin():
            return await queue_verification_email(
                db,
                customer_id=customer_id,
                encryption_key=key,
                now=now,
            )


async def state(factory, customer_id):
    async with factory() as db:
        customer = await db.get(Customer, customer_id)
        token = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id == customer_id
            )
        )
        outbox = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id == customer_id
            )
        )

        return (
            customer.email_verified_at if customer else None,
            token.token_hash if token else None,
            outbox.token_hash if outbox else None,
            outbox.encrypted_token if outbox else None,
            outbox.status if outbox else None,
            outbox.attempts if outbox else None,
            outbox.id if outbox else None,
        )


@pytest.mark.asyncio
async def test_queue_encrypts_token_and_matches_db_hash(worker_database):
    customer_id = await create_customer(worker_database)
    key = new_key()

    result = await queue(worker_database, customer_id, key)
    verified, token_hash, queue_hash, encrypted, status, attempts, row_id = (
        await state(worker_database, customer_id)
    )

    raw = decrypt_token(encrypted, key)

    assert result.customer_id == customer_id
    assert result.outbox_id == row_id
    assert result.expires_at == NOW + timedelta(minutes=30)
    assert token_hash == queue_hash == hash_token(raw)
    assert raw not in encrypted
    assert status == "pending"
    assert attempts == 0
    assert verified is None


@pytest.mark.asyncio
async def test_cooldown_preserves_existing_queue(worker_database):
    customer_id = await create_customer(worker_database)
    key = new_key()

    await queue(worker_database, customer_id, key)
    before = await state(worker_database, customer_id)

    with pytest.raises(VerificationCooldownError):
        await queue(
            worker_database,
            customer_id,
            key,
            NOW + timedelta(seconds=59),
        )

    assert await state(worker_database, customer_id) == before


@pytest.mark.asyncio
async def test_resend_replaces_token_and_reuses_queue_row(
    worker_database,
):
    customer_id = await create_customer(worker_database)
    key = new_key()

    await queue(worker_database, customer_id, key)
    before = await state(worker_database, customer_id)
    old_raw = decrypt_token(before[3], key)

    await queue(
        worker_database,
        customer_id,
        key,
        NOW + timedelta(seconds=60),
    )
    after = await state(worker_database, customer_id)

    assert before[6] == after[6]
    assert before[1] != after[1]
    assert before[3] != after[3]
    assert after[1] == after[2]
    assert hash_token(decrypt_token(after[3], key)) == after[1]

    async with worker_database() as db:
        async with db.begin():
            assert not await consume_verification_token(
                db,
                raw_token=old_raw,
                now=NOW + timedelta(seconds=61),
            )


@pytest.mark.asyncio
async def test_caller_rollback_discards_token_and_queue(
    worker_database,
):
    customer_id = await create_customer(worker_database)

    async with worker_database() as db:
        await queue_verification_email(
            db,
            customer_id=customer_id,
            encryption_key=new_key(),
            now=NOW,
        )
        await db.rollback()

    after = await state(worker_database, customer_id)

    assert after[1] is None
    assert after[2] is None
    assert after[3] is None


@pytest.mark.asyncio
async def test_invalid_encryption_key_rolls_back_both_records(
    worker_database,
):
    customer_id = await create_customer(worker_database)

    with pytest.raises(ValueError):
        await queue(
            worker_database,
            customer_id,
            "invalid-encryption-key",
        )

    after = await state(worker_database, customer_id)

    assert after[1] is None
    assert after[2] is None


@pytest.mark.asyncio
async def test_verified_customer_cannot_queue_again(worker_database):
    customer_id = await create_customer(worker_database)
    key = new_key()

    await queue(worker_database, customer_id, key)
    before = await state(worker_database, customer_id)
    raw = decrypt_token(before[3], key)

    async with worker_database() as db:
        async with db.begin():
            assert await consume_verification_token(
                db,
                raw_token=raw,
                now=NOW + timedelta(minutes=1),
            )

    with pytest.raises(AlreadyVerifiedError):
        await queue(
            worker_database,
            customer_id,
            key,
            NOW + timedelta(minutes=2),
        )

    after = await state(worker_database, customer_id)

    assert after[0] is not None
    assert after[1] == before[1]
    assert after[2] == before[2]


@pytest.mark.asyncio
async def test_concurrent_queue_requests_allow_only_one(
    worker_database,
):
    customer_id = await create_customer(worker_database)
    key = new_key()

    async def attempt():
        try:
            await queue(worker_database, customer_id, key)
            return "queued"
        except VerificationCooldownError:
            return "cooldown"

    results = await asyncio.wait_for(
        asyncio.gather(attempt(), attempt()),
        timeout=20,
    )

    assert sorted(results) == ["cooldown", "queued"]

    after = await state(worker_database, customer_id)
    assert after[1] == after[2]
    assert after[4] == "pending"


@pytest.mark.asyncio
async def test_queue_rejects_unknown_customer(worker_database):
    with pytest.raises(ValueError, match="Customer does not exist"):
        await queue(
            worker_database,
            2147483647,
            new_key(),
        )


@pytest.mark.asyncio
async def test_resend_resets_delivery_state(worker_database):
    customer_id = await create_customer(worker_database)
    key = new_key()

    await queue(worker_database, customer_id, key)

    async with worker_database() as db:
        async with db.begin():
            record = await db.scalar(
                select(VerificationEmailOutbox).where(
                    VerificationEmailOutbox.customer_id == customer_id
                )
            )
            record.status = "failed"
            record.attempts = 5
            record.last_error = "TEST_ERROR"
            record.sent_at = NOW

    await queue(
        worker_database,
        customer_id,
        key,
        NOW + timedelta(seconds=60),
    )

    async with worker_database() as db:
        record = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id == customer_id
            )
        )

        assert record.status == "pending"
        assert record.attempts == 0
        assert record.last_error is None
        assert record.sent_at is None
        assert record.claim_token is None
        assert record.lease_expires_at is None
