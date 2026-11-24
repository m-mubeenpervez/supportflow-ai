"""Isolated PostgreSQL tests for verification delivery status.

Uses the established worker_database temporary-schema fixture.
No real SMTP calls, no development database modifications.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.models import Customer, VerificationEmailOutbox
from app.verification_email_queue import queue_verification_email
from app.verification_email_worker import claim_verification_email
from app.verification_delivery_state import (
    mark_verification_sent,
    mark_verification_failed,
    retire_verification_claim,
)

from test_email_worker_integration import worker_database


def utc_now():
    return datetime.now(timezone.utc)


async def prepare(factory):
    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Delivery State Test",
                email=f"state-{uuid.uuid4().hex}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()

            await queue_verification_email(
                db,
                customer_id=customer.id,
                encryption_key=Fernet.generate_key().decode("ascii"),
                now=utc_now(),
            )

            customer_id = customer.id

    job = await claim_verification_email(
        session_factory=factory,
        allow_mock_delivery=True,
    )

    assert job is not None
    assert job.customer_id == customer_id

    return job


async def read_state(factory, job):
    async with factory() as db:
        row = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.id == job.id
            )
        )

        assert row is not None

        return {
            "status": row.status,
            "attempts": row.attempts,
            "claim_token": row.claim_token,
            "lease_expires_at": row.lease_expires_at,
            "last_error": row.last_error,
            "sent_at": row.sent_at,
            "next_attempt_at": row.next_attempt_at,
            "token_hash": row.token_hash,
        }


@pytest.mark.asyncio
async def test_success_marks_sent(worker_database):
    job = await prepare(worker_database)

    result = await mark_verification_sent(job, worker_database)

    assert result is True

    state = await read_state(worker_database, job)

    assert state["status"] == "sent"
    assert state["sent_at"] is not None
    assert state["claim_token"] is None
    assert state["lease_expires_at"] is None
    assert state["last_error"] is None


@pytest.mark.asyncio
async def test_same_claim_cannot_mark_sent_twice(worker_database):
    job = await prepare(worker_database)

    assert await mark_verification_sent(
        job, worker_database
    )

    assert not await mark_verification_sent(
        job, worker_database
    )


@pytest.mark.asyncio
async def test_failure_schedules_retry(worker_database):
    job = await prepare(worker_database)

    result = await mark_verification_failed(
        job,
        RuntimeError("PRIVATE SMTP DETAILS"),
        worker_database,
    )

    assert result == "retry"

    state = await read_state(worker_database, job)

    assert state["status"] == "pending"
    assert state["attempts"] == 1
    assert state["claim_token"] is None
    assert state["lease_expires_at"] is None
    assert state["last_error"] == "RuntimeError"
    assert "PRIVATE SMTP DETAILS" not in state["last_error"]
    assert state["next_attempt_at"] > utc_now()


@pytest.mark.asyncio
async def test_last_attempt_marks_failed(worker_database):
    job = await prepare(worker_database)

    maximum = settings.email_max_attempts
    assert maximum >= 1

    async with worker_database() as db:
        async with db.begin():
            row = await db.get(VerificationEmailOutbox, job.id)
            row.attempts = maximum

    final_job = replace(job, attempts=maximum)

    result = await mark_verification_failed(
        final_job,
        TimeoutError("SECRET"),
        worker_database,
    )

    assert result == "failed"

    state = await read_state(worker_database, job)

    assert state["status"] == "failed"
    assert state["last_error"] == "TimeoutError"
    assert state["claim_token"] is None


@pytest.mark.asyncio
async def test_stale_worker_cannot_mark_sent(worker_database):
    job = await prepare(worker_database)

    stale = replace(
        job,
        claim_token=str(uuid.uuid4()),
    )

    assert not await mark_verification_sent(
        stale, worker_database
    )

    state = await read_state(worker_database, job)

    assert state["status"] == "processing"
    assert state["claim_token"] == job.claim_token


@pytest.mark.asyncio
async def test_expired_lease_blocks_finalization(worker_database):
    job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            row = await db.get(VerificationEmailOutbox, job.id)
            row.lease_expires_at = (
                utc_now() - timedelta(seconds=1)
            )

    assert not await mark_verification_sent(
        job, worker_database
    )

    result = await mark_verification_failed(
        job,
        RuntimeError("EXPIRED"),
        worker_database,
    )

    assert result == "ownership_lost"

    state = await read_state(worker_database, job)

    assert state["status"] == "processing"


@pytest.mark.asyncio
async def test_invalid_job_can_be_retired(worker_database):
    job = await prepare(worker_database)

    result = await retire_verification_claim(
        job, worker_database
    )

    assert result is True

    state = await read_state(worker_database, job)

    assert state["status"] == "failed"
    assert state["claim_token"] is None
    assert state["lease_expires_at"] is None
    assert state["last_error"] == "Verification job ineligible"


@pytest.mark.asyncio
async def test_replaced_token_prevents_old_worker_update(
    worker_database,
):
    job = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            row = await db.get(VerificationEmailOutbox, job.id)
            row.token_hash = "a" * 64

    assert not await mark_verification_sent(
        job, worker_database
    )

    result = await mark_verification_failed(
        job,
        RuntimeError("STALE"),
        worker_database,
    )

    assert result == "ownership_lost"

    state = await read_state(worker_database, job)

    assert state["status"] == "processing"
    assert state["token_hash"] == "a" * 64
