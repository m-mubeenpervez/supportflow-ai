"""End-to-end outbox wiring, isolated DB; no SMTP, Gemini, or refunds."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import main
from app.auth import create_access_token
from app.models import Customer, EmailOutbox, Notification, Ticket


@pytest.mark.asyncio
@pytest.mark.parametrize("approve", [True, False])
async def test_approval_emails_are_queued_only_for_verified_owner(
    monkeypatch, postgres_session, approve
):
    monkeypatch.setattr(main, "Session", postgres_session)
    monkeypatch.setattr(main.settings, "email_delivery_enabled", True)
    monkeypatch.setattr(main.settings, "email_delivery_mode", "production")
    monkeypatch.setattr(
        main.settings, "admin_notification_email", "admin@example.test"
    )
    monkeypatch.setattr(
        main, "graph", SimpleNamespace(ainvoke=AsyncMock(return_value={
            "intent": "refund", "order_id": None,
            "draft": "Human review required. No payment processed.",
            "needs_approval": True, "sources": [],
        }))
    )
    async with postgres_session() as db:
        owner = Customer(
            name="Verified Test Customer",
            email=f"sf-email-{uuid4().hex}@example.test",
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(owner)
        await db.flush()
        owner_id, owner_email = owner.id, owner.email
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        customer_headers = {
            "Authorization": f"Bearer {create_access_token(owner_id)}"
        }
        admin_headers = {"X-Admin-Token": main.settings.admin_token}
        submitted = await client.post(
            "/chat", headers=customer_headers,
            json={"message": "Please review my refund request"},
        )
        assert submitted.status_code == 200, submitted.text
        ticket_id = submitted.json()["ticket_id"]
        assert submitted.json()["status"] == "pending_approval"
        decision = await client.post(
            f"/tickets/{ticket_id}/decision", headers=admin_headers,
            json={"approve": approve, "note": "Review only; no payment"},
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == (
            "approved" if approve else "rejected"
        )
        assert "no financial" in decision.json()["note"].lower()

    async with postgres_session() as db:
        notices = (await db.scalars(
            select(Notification).where(Notification.ticket_id == ticket_id)
        )).all()
        jobs = (await db.scalars(
            select(EmailOutbox).where(
                EmailOutbox.notification_id.in_([n.id for n in notices])
            )
        )).all()
        assert len(notices) == 2
        assert len(jobs) == 2
        assert {job.recipient_email for job in jobs} == {
            "admin@example.test", owner_email
        }
        customer_job = next(
            job for job in jobs if job.recipient_email == owner_email
        )
        assert "does not mean" in customer_job.body if approve else (
            "not approved" in customer_job.body
        )
        assert (await db.get(Ticket, ticket_id)).status == (
            "approved" if approve else "rejected"
        )


@pytest.mark.asyncio
async def test_notification_emails_remain_opt_in(monkeypatch, postgres_session):
    monkeypatch.setattr(main, "Session", postgres_session)
    monkeypatch.setattr(main.settings, "email_delivery_enabled", False)
    monkeypatch.setattr(
        main.settings, "admin_notification_email", "admin@example.test"
    )
    monkeypatch.setattr(
        main, "graph", SimpleNamespace(ainvoke=AsyncMock(return_value={
            "intent": "refund", "order_id": None,
            "draft": "Review required", "needs_approval": True, "sources": [],
        }))
    )
    async with postgres_session() as db:
        owner = Customer(
            name="No Email Test Customer",
            email=f"sf-disabled-{uuid4().hex}@example.test",
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(owner)
        await db.flush()
        owner_id = owner.id
        await db.commit()
    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/chat",
            headers={"Authorization": f"Bearer {create_access_token(owner_id)}"},
            json={"message": "Review a refund request"},
        )
        assert res.status_code == 200, res.text
        ticket_id = res.json()["ticket_id"]
    async with postgres_session() as db:
        notices = (await db.scalars(
            select(Notification).where(Notification.ticket_id == ticket_id)
        )).all()
        jobs = (await db.scalars(
            select(EmailOutbox).where(
                EmailOutbox.notification_id.in_([n.id for n in notices])
            )
        )).all()
        assert len(notices) == 1
        assert jobs == []
