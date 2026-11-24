"""Account lifecycle notices: isolated PostgreSQL transaction and worker tests."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from app import admin_management
from app.config import settings
from app.customer_action_email_worker import process_one_account_notice
from app.models import Customer, CustomerActionEmailOutbox, Ticket


def actor(role):
    return SimpleNamespace(id=987, email=f"{role}@example.invalid", role=role)


async def seed(db, address, *, active=True, verified=True):
    customer = Customer(
        email=address,
        name="Test Customer",
        password_hash="test-password-hash",
        email_verified_at=datetime.now(timezone.utc) if verified else None,
        deactivated_at=None if active else datetime.now(timezone.utc),
        session_version=1,
    )
    db.add(customer)
    await db.flush()
    db.add(Ticket(customer_id=customer.id, summary="Retained", intent="general"))
    await db.flush()
    return customer.id


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "super_admin"])
async def test_deactivate_schedules_email_transactionally(postgres_session, monkeypatch, role):
    monkeypatch.setattr(settings, "email_delivery_enabled", True)
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    async with postgres_session() as db:
        async with db.begin():
            customer_id = await seed(db, f"{role}-active@example.invalid")
    response = await admin_management.change_customer_status(
        customer_id, admin_management.AccountAction(reason="Staff action"), False, actor(role)
    )
    assert response["is_active"] is False
    async with postgres_session() as db:
        rows = (await db.scalars(select(CustomerActionEmailOutbox).where(
            CustomerActionEmailOutbox.customer_id == customer_id
        ))).all()
        assert len(rows) == 1
        assert rows[0].kind == "deactivated"
        assert rows[0].status == "pending"
        assert rows[0].recipient_email == f"{role}-active@example.invalid"


@pytest.mark.asyncio
async def test_removal_cancels_old_notice_and_queues_final_notice(postgres_session, monkeypatch):
    monkeypatch.setattr(settings, "email_delivery_enabled", True)
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    async with postgres_session() as db:
        async with db.begin():
            customer_id = await seed(db, "removed-notice@example.invalid")
    await admin_management.change_customer_status(
        customer_id, admin_management.AccountAction(reason="Staff action"), False, actor("super_admin")
    )
    response = await admin_management.delete_customer(
        customer_id, admin_management.AccountAction(reason="Account removal"), actor("super_admin")
    )
    assert response["deleted"] is True
    async with postgres_session() as db:
        rows = (await db.scalars(select(CustomerActionEmailOutbox).where(
            CustomerActionEmailOutbox.customer_id == customer_id
        ).order_by(CustomerActionEmailOutbox.id))).all()
        assert len(rows) == 2
        assert rows[0].kind == "deactivated" and rows[0].status == "cancelled"
        assert rows[0].recipient_email.endswith("@deleted.invalid")
        assert rows[1].kind == "removed" and rows[1].status == "pending"
        assert rows[1].recipient_email == "removed-notice@example.invalid"
        customer = await db.get(Customer, customer_id)
        assert customer.deleted_at is not None
        assert customer.email.endswith("@deleted.invalid")
        assert await db.scalar(select(func.count(Ticket.id)).where(Ticket.customer_id == customer_id)) == 1


@pytest.mark.asyncio
async def test_no_email_queue_when_disabled_or_unverified(postgres_session, monkeypatch):
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    monkeypatch.setattr(settings, "email_delivery_enabled", False)
    async with postgres_session() as db:
        async with db.begin():
            customer_id = await seed(db, "disabled@example.invalid")
    await admin_management.change_customer_status(
        customer_id, admin_management.AccountAction(reason="Staff action"), False, actor("admin")
    )
    monkeypatch.setattr(settings, "email_delivery_enabled", True)
    async with postgres_session() as db:
        async with db.begin():
            other_id = await seed(db, "unverified@example.invalid", verified=False)
    await admin_management.change_customer_status(
        other_id, admin_management.AccountAction(reason="Staff action"), False, actor("admin")
    )
    async with postgres_session() as db:
        assert await db.scalar(select(func.count(CustomerActionEmailOutbox.id)).where(
            CustomerActionEmailOutbox.customer_id.in_([customer_id, other_id])
        )) == 0


@pytest.mark.asyncio
async def test_worker_delivery_redacts_address(postgres_session, monkeypatch):
    monkeypatch.setattr(settings, "email_delivery_enabled", True)
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    async with postgres_session() as db:
        async with db.begin():
            customer_id = await seed(db, "notice-sent@example.invalid")
    await admin_management.change_customer_status(
        customer_id, admin_management.AccountAction(reason="Staff action"), False, actor("admin")
    )
    sent = []

    async def fake_sender(email, subject, body):
        sent.append((email, subject, body))

    result = await process_one_account_notice(session_factory=postgres_session, sender=fake_sender)
    assert result == "sent"
    assert len(sent) == 1
    assert sent[0][0] == "notice-sent@example.invalid"
    async with postgres_session() as db:
        notice = await db.scalar(select(CustomerActionEmailOutbox).where(
            CustomerActionEmailOutbox.customer_id == customer_id
        ))
        assert notice.status == "sent"
        assert notice.sent_at is not None
        assert notice.recipient_email.endswith("@deleted.invalid")

@pytest.mark.asyncio
async def test_existing_email_runner_drains_account_queue(postgres_session, monkeypatch):
    """SMTP batch runner handles account notices even without support tickets."""
    from app.email_runner import run_batch

    monkeypatch.setattr(settings, "email_delivery_enabled", True)
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    async with postgres_session() as db:
        async with db.begin():
            customer_id = await seed(db, "batch-notice@example.invalid")
    await admin_management.change_customer_status(
        customer_id, admin_management.AccountAction(reason="Staff action"), False, actor("admin")
    )
    delivered = []

    async def fake_sender(email, subject, body):
        delivered.append(email)

    summary = await run_batch(session_factory=postgres_session, sender=fake_sender, batch_size=5)
    assert summary.sent == 1
    assert delivered == ["batch-notice@example.invalid"]
