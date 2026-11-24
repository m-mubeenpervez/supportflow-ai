"""End-to-end verification delivery tests with fake SMTP.

Uses isolated PostgreSQL test schemas. Never sends real email.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.email_verification import hash_token
from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from app.verification_delivery_processor import (
    build_verification_url,
    process_one_verification_email,
)
from app.verification_email_queue import queue_verification_email

from test_email_worker_integration import worker_database


BASE_URL = "http://localhost:5173/verify-email"


def now():
    return datetime.now(timezone.utc)


async def prepare(factory):
    key = Fernet.generate_key().decode("ascii")

    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Delivery Processor Test",
                email=f"processor-{uuid.uuid4().hex}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()

            customer_id = customer.id

            await queue_verification_email(
                db,
                customer_id=customer_id,
                encryption_key=key,
                now=now(),
            )

    return customer_id, key


async def read_state(factory, customer_id):
    async with factory() as db:
        queue = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id == customer_id
            )
        )

        token = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id == customer_id
            )
        )

        return {
            "status": queue.status,
            "attempts": queue.attempts,
            "claim_token": queue.claim_token,
            "last_error": queue.last_error,
            "sent_at": queue.sent_at,
            "queue_hash": queue.token_hash,
            "active_hash": token.token_hash,
        }


async def process(factory, key, sender):
    return await process_one_verification_email(
        session_factory=factory,
        sender=sender,
        encryption_key=key,
        verification_base_url=BASE_URL,
        allow_mock_delivery=True,
    )


def extract_token(body):
    marker = BASE_URL + "?token="

    assert marker in body

    url = body.split(marker, 1)[1].split()[0]
    candidate = marker + url

    parsed = urlsplit(candidate)

    values = parse_qs(parsed.query)
    assert len(values.get("token", [])) == 1

    return values["token"][0]


@pytest.mark.asyncio
async def test_successful_fake_delivery(worker_database):
    customer_id, key = await prepare(worker_database)
    captured = []

    async def fake_sender(recipient, subject, body):
        captured.append((recipient, subject, body))

    result = await process(worker_database, key, fake_sender)
    state = await read_state(worker_database, customer_id)

    assert result == "sent"
    assert len(captured) == 1
    assert captured[0][0].endswith("@example.test")
    assert captured[0][1] == "Verify your SupportFlow AI email"
    assert state["status"] == "sent"
    assert state["sent_at"] is not None
    assert state["claim_token"] is None


@pytest.mark.asyncio
async def test_email_link_matches_active_token(worker_database):
    customer_id, key = await prepare(worker_database)
    messages = []

    async def fake_sender(recipient, subject, body):
        messages.append(body)

    assert await process(
        worker_database, key, fake_sender
    ) == "sent"

    raw_token = extract_token(messages[0])
    state = await read_state(worker_database, customer_id)

    assert hash_token(raw_token) == state["active_hash"]
    assert state["queue_hash"] == state["active_hash"]


@pytest.mark.asyncio
async def test_disabled_delivery_does_not_claim(worker_database):
    customer_id, key = await prepare(worker_database)

    result = await process_one_verification_email(
        session_factory=worker_database,
        encryption_key=key,
        verification_base_url=BASE_URL,
    )

    assert result == "disabled"

    state = await read_state(worker_database, customer_id)

    assert state["status"] == "pending"
    assert state["attempts"] == 0


@pytest.mark.asyncio
async def test_invalid_key_rejected_before_claim(worker_database):
    customer_id, _ = await prepare(worker_database)

    async def fake_sender(*args):
        raise AssertionError("Sender must not be called")

    with pytest.raises(ValueError):
        await process(
            worker_database,
            "invalid-key",
            fake_sender,
        )

    state = await read_state(worker_database, customer_id)
    assert state["status"] == "pending"
    assert state["attempts"] == 0


@pytest.mark.asyncio
async def test_fake_smtp_failure_schedules_retry(worker_database):
    customer_id, key = await prepare(worker_database)

    async def failing_sender(*args):
        raise TimeoutError("FAKE PRIVATE SMTP RESPONSE")

    result = await process(
        worker_database, key, failing_sender
    )

    state = await read_state(worker_database, customer_id)

    assert result == "retry"
    assert state["status"] == "pending"
    assert state["attempts"] == 1
    assert state["last_error"] == "TimeoutError"
    assert state["claim_token"] is None


@pytest.mark.asyncio
async def test_verified_customer_never_sent(worker_database):
    customer_id, key = await prepare(worker_database)

    async with worker_database() as db:
        async with db.begin():
            customer = await db.get(Customer, customer_id)
            customer.email_verified_at = now()

    calls = []

    async def fake_sender(*args):
        calls.append(args)

    result = await process(
        worker_database, key, fake_sender
    )

    assert result == "empty"
    assert calls == []


@pytest.mark.asyncio
async def test_resend_during_send_preserves_new_queue(
    worker_database,
):
    customer_id, key = await prepare(worker_database)

    started = asyncio.Event()
    release = asyncio.Event()
    old_messages = []

    async def paused_sender(recipient, subject, body):
        old_messages.append(body)
        started.set()
        await asyncio.wait_for(release.wait(), timeout=10)

    task = asyncio.create_task(
        process(worker_database, key, paused_sender)
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=10)

        old_token = extract_token(old_messages[0])

        # Simulate an allowed resend after the 60-second cooldown.
        async with worker_database() as db:
            async with db.begin():
                await queue_verification_email(
                    db,
                    customer_id=customer_id,
                    encryption_key=key,
                    now=now() + timedelta(seconds=61),
                )

    finally:
        release.set()

    result = await asyncio.wait_for(task, timeout=10)
    state = await read_state(worker_database, customer_id)

    assert result == "ownership_lost"
    assert state["status"] == "pending"
    assert state["claim_token"] is None
    assert state["queue_hash"] == state["active_hash"]
    assert hash_token(old_token) != state["active_hash"]
