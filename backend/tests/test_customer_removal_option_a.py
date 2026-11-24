"""Option A deletion: actual PostgreSQL isolated-test-schema integration checks."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models import (
    Customer, Ticket, Order, Message, EmailVerificationToken,
    VerificationEmailOutbox, Notification, EmailOutbox,
)
from app.customer_removal import anonymize_customer_account
from app.email_recipients import customer_notification_recipient
from app import admin_management
from app.admin_activity import AdminActivity


async def seed_customer(session, email: str, active: bool = False):
    customer = Customer(
        name="Visible Person", email=email,
        password_hash="old-hash-must-disappear",
        email_verified_at=datetime.now(timezone.utc),
        deactivated_at=None if active else datetime.now(timezone.utc),
        session_version=3,
    )
    session.add(customer)
    await session.flush()
    ticket = Ticket(customer_id=customer.id, summary="Historical ticket", intent="general")
    order = Order(id=f"OPT-A-{customer.id}", customer_id=customer.id,
                  item="Historical item", status="delivered", total=50)
    session.add_all([ticket, order])
    await session.flush()
    session.add(Message(ticket_id=ticket.id, role="customer", content="Historical message"))
    return customer, ticket, order


@pytest.mark.asyncio
async def test_removal_keeps_support_history_and_removes_profile(postgres_session):
    async with postgres_session() as db:
        async with db.begin():
            customer, ticket, order = await seed_customer(db, "alpha@example.invalid")
            customer_id, ticket_id, order_id = customer.id, ticket.id, order.id
            result = await anonymize_customer_account(db, customer)
            assert result["deleted"] is True
            assert result["history_preserved"] is True
            assert result["method"] == "anonymized_tombstone"
        await db.refresh(customer)
        assert customer.deleted_at is not None
        assert customer.password_hash is None
        assert customer.email_verified_at is None
        assert customer.deactivated_at is not None
        assert customer.email != "alpha@example.invalid"
        assert "@deleted.invalid" in customer.email
        assert customer.session_version == 4
        assert await db.get(Ticket, ticket_id) is not None
        assert await db.get(Order, order_id) is not None
        assert await db.scalar(select(func.count(Message.id)).where(Message.ticket_id == ticket_id)) == 1
        assert (await db.get(Ticket, ticket_id)).customer_id == customer_id
        assert customer_notification_recipient(customer) is None
        # Original email may be reused by a newly registering customer; history
        # remains attached to the old anonymized customer ID.
        new_customer = Customer(
            name="New Account",
            email="alpha@example.invalid",
            password_hash="new-hash",
        )
        db.add(new_customer)
        await db.flush()
        assert new_customer.id != customer_id
        assert (await db.get(Ticket, ticket_id)).customer_id == customer_id


@pytest.mark.asyncio
async def test_removal_clears_tokens_and_cancels_email(postgres_session):
    async with postgres_session() as db:
        async with db.begin():
            customer, ticket, _ = await seed_customer(db, "beta@example.invalid")
            now = datetime.now(timezone.utc)
            db.add(EmailVerificationToken(
                customer_id=customer.id, token_hash="a" * 64,
                expires_at=now + timedelta(days=1), last_sent_at=now,
            ))
            db.add(VerificationEmailOutbox(
                customer_id=customer.id, token_hash="a" * 64,
                encrypted_token="sensitive-encrypted-content",
                expires_at=now + timedelta(days=1), status="pending",
                attempts=0, next_attempt_at=now,
            ))
            notification = Notification(
                event_key=f"customer:{customer.id}:delete-test",
                recipient_type="customer", customer_id=customer.id,
                ticket_id=ticket.id, event_type="test", title="Test", body="Notice"
            )
            db.add(notification)
            await db.flush()
            outbox = EmailOutbox(
                notification_id=notification.id,
                recipient_email="beta@example.invalid",
                subject="Sensitive subject", body="Sensitive message", status="pending"
            )
            db.add(outbox)
            await db.flush()
            outbox_id = outbox.id
            customer_id = customer.id
            await anonymize_customer_account(db, customer)
        assert await db.scalar(select(func.count(EmailVerificationToken.id)).where(EmailVerificationToken.customer_id == customer_id)) == 0
        assert await db.scalar(select(func.count(VerificationEmailOutbox.id)).where(VerificationEmailOutbox.customer_id == customer_id)) == 0
        # Bulk UPDATE expires ORM attributes in SQLAlchemy. Read the stored
        # columns with an explicit async query to avoid implicit synchronous
        # I/O (MissingGreenlet) while still asserting the database state.
        preserved = (await db.execute(
            select(
                EmailOutbox.status,
                EmailOutbox.recipient_email,
                EmailOutbox.body,
            ).where(EmailOutbox.id == outbox_id)
        )).one()
        assert preserved.status == "cancelled"
        assert preserved.recipient_email.endswith("@deleted.invalid")
        assert preserved.body != "Sensitive message"


@pytest.mark.asyncio
async def test_active_account_cannot_be_removed(postgres_session):
    async with postgres_session() as db:
        async with db.begin():
            customer, ticket, _ = await seed_customer(db, "active@example.invalid", active=True)
            with pytest.raises(HTTPException) as exc:
                await anonymize_customer_account(db, customer)
            assert exc.value.status_code == 409
            assert customer.deleted_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "super_admin"])
async def test_both_admin_roles_remove_deactivated_customer(postgres_session, monkeypatch, role):
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    async with postgres_session() as db:
        async with db.begin():
            customer, _, _ = await seed_customer(db, f"role-{role}@example.invalid")
            customer_id = customer.id
    actor = SimpleNamespace(id=987, email=f"{role}@example.invalid", role=role)
    response = await admin_management.delete_customer(
        customer_id, admin_management.AccountAction(reason="Account closed"), actor
    )
    assert response["deleted"] is True
    async with postgres_session() as db:
        assert (await db.get(Customer, customer_id)).deleted_at is not None
        assert await db.scalar(select(func.count(AdminActivity.id)).where(
            AdminActivity.entity_type == "customer",
            AdminActivity.entity_id == customer_id,
            AdminActivity.action == "customer_account_removed",
        )) == 1


@pytest.mark.asyncio
async def test_pending_human_approval_blocks_removal(postgres_session):
    async with postgres_session() as db:
        async with db.begin():
            customer, ticket, _ = await seed_customer(db, "pending@example.invalid")
            ticket.status = "pending_approval"
            await db.flush()
            with pytest.raises(HTTPException) as exc:
                await anonymize_customer_account(db, customer)
            assert exc.value.status_code == 409
            assert customer.deleted_at is None


@pytest.mark.asyncio
async def test_removed_customer_cannot_be_reactivated(postgres_session, monkeypatch):
    monkeypatch.setattr(admin_management, "Session", postgres_session)
    async with postgres_session() as db:
        async with db.begin():
            customer, _, _ = await seed_customer(db, "removed@example.invalid")
            customer_id = customer.id
            await anonymize_customer_account(db, customer)

    actor = SimpleNamespace(id=987, email="staff@example.invalid", role="admin")
    with pytest.raises(HTTPException) as exc:
        await admin_management.change_customer_status(
            customer_id,
            admin_management.AccountAction(reason="Reactivation attempt"),
            True,
            actor,
        )
    assert exc.value.status_code == 404
