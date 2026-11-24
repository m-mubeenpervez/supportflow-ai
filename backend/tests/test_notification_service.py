"""Isolated tests for persistent notification services."""

import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models import Customer, Ticket, Notification, EmailOutbox
from app.notification_service import (
    create_notification,
    notify_admin_approval_requested,
    notify_customer_decision,
)


async def make_ticket(session, status="pending_approval"):
    customer = Customer(
        name="Notification Test Customer",
        email=f"notification-{status}-{id(session)}@test.local",
        password_hash="TEST_ONLY",
    )
    session.add(customer)
    await session.flush()

    ticket = Ticket(
        customer_id=customer.id,
        intent="refund",
        status=status,
        summary="Notification test ticket",
    )
    session.add(ticket)
    await session.flush()
    return customer, ticket


@pytest.mark.asyncio
async def test_admin_notification_and_email_outbox(postgres_session):
    async with postgres_session() as db:
        customer, ticket = await make_ticket(db)

        notification = await notify_admin_approval_requested(
            db,
            ticket=ticket,
            admin_email="admin@test.local",
        )

        await db.flush()

        assert notification.recipient_type == "admin"
        assert notification.customer_id is None
        assert notification.ticket_id == ticket.id
        assert notification.event_type == "approval_requested"
        assert notification.read_at is None

        email = await db.scalar(
            select(EmailOutbox).where(
                EmailOutbox.notification_id == notification.id
            )
        )

        assert email is not None
        assert email.recipient_email == "admin@test.local"
        assert email.status == "pending"
        assert email.attempts == 0

        print("Admin notification and email outbox: PASS")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["approved", "rejected"])
async def test_customer_decision_notification(
    postgres_session,
    status,
):
    async with postgres_session() as db:
        customer, ticket = await make_ticket(db, status)

        notification = await notify_customer_decision(
            db,
            ticket=ticket,
        )

        await db.flush()

        assert notification.recipient_type == "customer"
        assert notification.customer_id == customer.id
        assert notification.ticket_id == ticket.id
        assert notification.event_type == f"request_{status}"
        assert notification.read_at is None

        if status == "approved":
            assert "does not mean" in notification.body

        print(f"Customer {status} notification: PASS")


@pytest.mark.asyncio
async def test_duplicate_notification_rejected(postgres_session):
    async with postgres_session() as db:
        _, ticket = await make_ticket(db)

        await notify_admin_approval_requested(db, ticket=ticket)
        await db.flush()

        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await notify_admin_approval_requested(
                    db,
                    ticket=ticket,
                )
                await db.flush()

        print("Duplicate event prevention: PASS")


@pytest.mark.asyncio
async def test_invalid_recipient_rejected(postgres_session):
    async with postgres_session() as db:
        _, ticket = await make_ticket(db)

        with pytest.raises(ValueError):
            await create_notification(
                db,
                event_key="invalid-recipient",
                recipient_type="customer",
                ticket_id=ticket.id,
                event_type="test",
                title="Test",
                body="Test",
                customer_id=None,
            )

        with pytest.raises(ValueError):
            await create_notification(
                db,
                event_key="invalid-admin",
                recipient_type="admin",
                ticket_id=ticket.id,
                event_type="test",
                title="Test",
                body="Test",
                customer_id=ticket.customer_id,
            )

        print("Recipient validation: PASS")


@pytest.mark.asyncio
async def test_notification_rollback(postgres_session):
    async with postgres_session() as db:
        _, ticket = await make_ticket(db)

        async with db.begin_nested() as transaction:
            await notify_admin_approval_requested(
                db,
                ticket=ticket,
            )
            await db.flush()
            await transaction.rollback()

        count = await db.scalar(
            select(func.count(Notification.id)).where(
                Notification.ticket_id == ticket.id
            )
        )

        assert count == 0

        print("Notification transaction rollback: PASS")
