"""End-to-end notification workflow with mocked AI."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import main
from app.auth import create_access_token
from app.models import (
    Audit,
    Customer,
    EmailOutbox,
    Notification,
    Ticket,
)


@pytest.mark.asyncio
async def test_refund_notification_workflow(
    monkeypatch,
    postgres_session,
):
    monkeypatch.setattr(
        main,
        "Session",
        postgres_session,
    )

    fake_graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "intent": "refund",
                "order_id": None,
                "draft": (
                    "Your request requires human review. "
                    "No refund has been processed."
                ),
                "needs_approval": True,
                "sources": [],
            }
        )
    )

    monkeypatch.setattr(main, "graph", fake_graph)

    assert main.settings.admin_token
    assert main.settings.jwt_secret_key

    async with postgres_session() as db:
        customer = Customer(
            name="Workflow Test Customer",
            email=(
                f"workflow-{uuid4().hex}@test.local"
            ),
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(customer)
        await db.flush()
        customer_id = customer.id
        await db.commit()

    customer_headers = {
        "Authorization": (
            f"Bearer {create_access_token(customer_id)}"
        )
    }

    admin_headers = {
        "X-Admin-Token": main.settings.admin_token
    }

    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:

        # Step 1: Customer submits a refund request.
        response = await client.post(
            "/chat",
            json={
                "message": (
                    "Please review my fictional refund request."
                )
            },
            headers=customer_headers,
        )

        assert response.status_code == 200, response.text

        result = response.json()

        assert result["status"] == "pending_approval"
        assert result["intent"] == "refund"

        ticket_id = result["ticket_id"]

        fake_graph.ainvoke.assert_awaited_once()

        print("Customer refund request: PASS")

        # Step 2: Verify admin notification via API.
        response = await client.get(
            "/notifications/admin",
            headers=admin_headers,
        )

        assert response.status_code == 200

        admin_items = [
            item for item in response.json()
            if item["ticket_id"] == ticket_id
            and item["event_type"] == "approval_requested"
        ]

        assert len(admin_items) == 1
        assert admin_items[0]["read_at"] is None

        print("Automatic admin notification: PASS")

        # Step 3: No customer decision before approval.
        response = await client.get(
            "/notifications/customer",
            headers=customer_headers,
        )

        assert response.status_code == 200

        initial_customer_items = [
            item for item in response.json()
            if item["ticket_id"] == ticket_id
        ]

        assert initial_customer_items == []

        print("No premature customer decision: PASS")

        # Step 4: Admin records approval.
        response = await client.post(
            f"/tickets/{ticket_id}/decision",
            json={
                "approve": True,
                "note": (
                    "TEST ONLY: Human approval recorded. "
                    "No payment executed."
                ),
            },
            headers=admin_headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "approved"

        print("Admin decision recording: PASS")

        # Step 5: Verify customer notification via API.
        response = await client.get(
            "/notifications/customer",
            headers=customer_headers,
        )

        assert response.status_code == 200

        customer_items = [
            item for item in response.json()
            if item["ticket_id"] == ticket_id
        ]

        assert len(customer_items) == 1
        assert (
            customer_items[0]["event_type"]
            == "request_approved"
        )
        assert (
            "does not mean"
            in customer_items[0]["body"]
        )

        print("Automatic customer notification: PASS")

        # Step 6: Duplicate admin decision must fail.
        response = await client.post(
            f"/tickets/{ticket_id}/decision",
            json={"approve": True},
            headers=admin_headers,
        )

        assert response.status_code == 409

        print("Duplicate decision protection: PASS")

    # Step 7: Verify all persisted records.
    async with postgres_session() as db:
        ticket = await db.get(Ticket, ticket_id)

        assert ticket is not None
        assert ticket.customer_id == customer_id
        assert ticket.status == "approved"
        assert ticket.approved is True

        notifications = (
            await db.scalars(
                select(Notification).where(
                    Notification.ticket_id == ticket_id
                )
            )
        ).all()

        assert len(notifications) == 2

        assert {
            item.recipient_type for item in notifications
        } == {"admin", "customer"}

        customer_notification = next(
            item for item in notifications
            if item.recipient_type == "customer"
        )

        assert (
            customer_notification.customer_id
            == customer_id
        )

        audits = (
            await db.scalars(
                select(Audit).where(
                    Audit.ticket_id == ticket_id
                )
            )
        ).all()

        assert sorted(
            audit.action for audit in audits
        ) == ["approved", "draft_created"]

        outbox_entries = (
            await db.scalars(
                select(EmailOutbox).where(
                    EmailOutbox.notification_id.in_(
                        [item.id for item in notifications]
                    )
                )
            )
        ).all()

        assert outbox_entries == []

    print("Database notification ownership: PASS")
    print("Audit records: PASS")
    print("Email delivery not triggered: PASS")
    print("Real refund execution not triggered: PASS")
    print("NOTIFICATION WORKFLOW: PASSED")
