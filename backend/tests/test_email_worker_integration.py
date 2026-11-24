"""Isolated PostgreSQL integration tests for email worker."""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app import email_worker
from app.db import Base
from app.models import Customer, EmailOutbox, Notification, Ticket
from postgres_test_config import get_test_database_url


@pytest_asyncio.fixture
async def worker_database():
    """Create and remove only this test's temporary schema."""

    database_url = get_test_database_url()
    url = make_url(database_url)

    if (
        url.drivername != "postgresql+asyncpg"
        or url.database != "supportflow_test_db"
    ):
        raise RuntimeError("Unsafe worker test database")

    schema = "sf_test_email_" + uuid.uuid4().hex[:16]

    admin_engine = create_async_engine(database_url)
    test_engine = None
    schema_created = False

    try:
        async with admin_engine.begin() as connection:
            actual = await connection.scalar(
                text("SELECT current_database()")
            )

            if actual != "supportflow_test_db":
                raise RuntimeError("Unexpected connected database")

            await connection.execute(
                text(f'CREATE SCHEMA "{schema}"')
            )
            schema_created = True

        test_engine = create_async_engine(
            database_url,
            connect_args={
                "server_settings": {
                    "search_path": schema
                }
            },
        )

        # Ensure all SQLAlchemy models are registered.
        import app.models  # noqa: F401

        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(
            test_engine,
            expire_on_commit=False,
        )

        yield factory

    finally:
        if test_engine is not None:
            await test_engine.dispose()

        if schema_created:
            # Only remove the uniquely named schema created above.
            async with admin_engine.begin() as connection:
                actual = await connection.scalar(
                    text("SELECT current_database()")
                )

                if (
                    actual != "supportflow_test_db"
                    or not schema.startswith("sf_test_email_")
                ):
                    raise RuntimeError("Unsafe test cleanup")

                await connection.execute(
                    text(f'DROP SCHEMA "{schema}" CASCADE')
                )

        await admin_engine.dispose()


async def create_queued_email(factory, suffix="one"):
    """Commit fictional test data visible to worker sessions."""

    unique = uuid.uuid4().hex

    async with factory() as db:
        async with db.begin():
            customer = Customer(
                name="Email Worker Test Customer",
                email=f"worker-{unique}@example.test",
                password_hash="TEST_ONLY",
            )
            db.add(customer)
            await db.flush()

            ticket = Ticket(
                customer_id=customer.id,
                intent="refund",
                status="pending_approval",
                summary="Fictional worker test",
            )
            db.add(ticket)
            await db.flush()

            notification = Notification(
                event_key=f"worker-test:{unique}:{suffix}",
                recipient_type="admin",
                ticket_id=ticket.id,
                event_type="approval_requested",
                title="Fictional approval request",
                body="Worker integration test only.",
            )
            db.add(notification)
            await db.flush()

            email = EmailOutbox(
                notification_id=notification.id,
                recipient_email="admin@example.test",
                subject="Fictional ticket notification",
                body="No real email should be sent.",
            )
            db.add(email)
            await db.flush()

            return email.id


async def read_email(factory, email_id):
    async with factory() as db:
        return await db.scalar(
            select(EmailOutbox).where(
                EmailOutbox.id == email_id
            )
        )


@pytest.mark.asyncio
async def test_success_marks_email_sent(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)
    sent_messages = []

    async def fake_sender(recipient, subject, body):
        sent_messages.append((recipient, subject, body))

    result = await email_worker.process_one(
        worker_database,
        sender=fake_sender,
    )

    email = await read_email(worker_database, email_id)

    assert result == "sent"
    assert len(sent_messages) == 1
    assert email.status == "sent"
    assert email.attempts == 1
    assert email.sent_at is not None
    assert email.claim_token is None
    assert email.lease_expires_at is None


@pytest.mark.asyncio
async def test_failure_schedules_retry(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)

    async def fake_failure(recipient, subject, body):
        raise ConnectionError("SIMULATED FAILURE")

    result = await email_worker.process_one(
        worker_database,
        sender=fake_failure,
    )

    email = await read_email(worker_database, email_id)

    assert result == "retry"
    assert email.status == "pending"
    assert email.attempts == 1
    assert email.next_attempt_at > datetime.now(timezone.utc)
    assert email.last_error == "ConnectionError"
    assert email.claim_token is None


@pytest.mark.asyncio
async def test_disabled_worker_does_not_claim(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        False,
    )

    email_id = await create_queued_email(worker_database)

    async def forbidden_sender(*args):
        raise AssertionError("Sender must not be called")

    result = await email_worker.process_one(
        worker_database,
        sender=forbidden_sender,
    )

    email = await read_email(worker_database, email_id)

    assert result == "disabled"
    assert email.status == "pending"
    assert email.attempts == 0


@pytest.mark.asyncio
async def test_concurrent_workers_do_not_duplicate_claim(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)
    sent_messages = []

    async def fake_sender(recipient, subject, body):
        await asyncio.sleep(0.05)
        sent_messages.append(recipient)

    results = await asyncio.gather(
        email_worker.process_one(
            worker_database,
            sender=fake_sender,
        ),
        email_worker.process_one(
            worker_database,
            sender=fake_sender,
        ),
    )

    email = await read_email(worker_database, email_id)

    assert sorted(results) == ["empty", "sent"]
    assert len(sent_messages) == 1
    assert email.status == "sent"
    assert email.attempts == 1


# ==========================================================
# STEP 26.53 - RECOVERY AND OWNERSHIP TESTS
# ==========================================================


@pytest.mark.asyncio
async def test_fifth_failure_is_terminal(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)

    async with worker_database() as db:
        async with db.begin():
            await db.execute(
                text("""
                    UPDATE email_outbox
                    SET attempts = 4,
                        next_attempt_at = NOW()
                            - INTERVAL '1 minute'
                    WHERE id = :id
                """),
                {"id": email_id},
            )

    async def failing_sender(*args):
        raise ConnectionError("Simulated final failure")

    result = await email_worker.process_one(
        worker_database,
        sender=failing_sender,
    )

    email = await read_email(worker_database, email_id)

    assert result == "failed"
    assert email.status == "failed"
    assert email.attempts == 5
    assert email.claim_token is None
    assert email.lease_expires_at is None
    assert email.last_error == "ConnectionError"

    assert await email_worker.claim_email(
        worker_database
    ) is None


@pytest.mark.asyncio
async def test_expired_exhausted_lease_recovery(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)

    async with worker_database() as db:
        async with db.begin():
            await db.execute(
                text("""
                    UPDATE email_outbox
                    SET status = 'processing',
                        attempts = 5,
                        claim_token = :token,
                        lease_expires_at =
                            NOW() - INTERVAL '1 minute'
                    WHERE id = :id
                """),
                {
                    "id": email_id,
                    "token": str(uuid.uuid4()),
                },
            )

    count = await email_worker.recover_exhausted(
        worker_database
    )

    email = await read_email(worker_database, email_id)

    assert count == 1
    assert email.status == "failed"
    assert email.attempts == 5
    assert email.claim_token is None
    assert email.lease_expires_at is None


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)

    old_claim = await email_worker.claim_email(
        worker_database
    )

    assert old_claim is not None
    assert old_claim.attempts == 1

    async with worker_database() as db:
        async with db.begin():
            await db.execute(
                text("""
                    UPDATE email_outbox
                    SET lease_expires_at =
                        NOW() - INTERVAL '1 minute'
                    WHERE id = :id
                """),
                {"id": email_id},
            )

    new_claim = await email_worker.claim_email(
        worker_database
    )

    assert new_claim is not None
    assert new_claim.id == email_id
    assert new_claim.attempts == 2
    assert new_claim.claim_token != old_claim.claim_token


@pytest.mark.asyncio
async def test_stale_worker_cannot_overwrite_new_owner(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)

    old_claim = await email_worker.claim_email(
        worker_database
    )

    assert old_claim is not None

    async with worker_database() as db:
        async with db.begin():
            await db.execute(
                text("""
                    UPDATE email_outbox
                    SET lease_expires_at =
                        NOW() - INTERVAL '1 minute'
                    WHERE id = :id
                """),
                {"id": email_id},
            )

    new_claim = await email_worker.claim_email(
        worker_database
    )

    assert new_claim is not None
    assert new_claim.claim_token != old_claim.claim_token

    old_result = await email_worker.mark_sent(
        old_claim,
        worker_database,
    )

    assert old_result is False

    email = await read_email(worker_database, email_id)

    assert email.status == "processing"
    assert email.claim_token == new_claim.claim_token

    new_result = await email_worker.mark_sent(
        new_claim,
        worker_database,
    )

    assert new_result is True

    email = await read_email(worker_database, email_id)

    assert email.status == "sent"
    assert email.claim_token is None


@pytest.mark.asyncio
async def test_active_lease_cannot_be_reclaimed(
    worker_database,
    monkeypatch,
):
    monkeypatch.setattr(
        email_worker.settings,
        "email_delivery_enabled",
        True,
    )

    email_id = await create_queued_email(worker_database)

    first_claim = await email_worker.claim_email(
        worker_database
    )

    second_claim = await email_worker.claim_email(
        worker_database
    )

    assert first_claim is not None
    assert first_claim.id == email_id
    assert second_claim is None

    email = await read_email(worker_database, email_id)

    assert email.status == "processing"
    assert email.attempts == 1
    assert email.claim_token == first_claim.claim_token
