"""Notification API authorization and ownership tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import main
from app.auth import create_access_token
from app.models import Customer, Notification, Ticket


@pytest.mark.asyncio
async def test_notification_api_security(monkeypatch, postgres_session):
    # All API database operations use the isolated test fixture.
    monkeypatch.setattr(main, "Session", postgres_session)

    assert main.settings.admin_token
    assert main.settings.jwt_secret_key

    unique = uuid4().hex

    async with postgres_session() as db:
        customer_a = Customer(
            name="Notification Customer A",
            email=f"notification-a-{unique}@test.local",
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )
        customer_b = Customer(
            name="Notification Customer B",
            email=f"notification-b-{unique}@test.local",
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )

        customer_c = Customer(
            name="Unverified Notification Customer",
            email=f"notification-c-{unique}@test.local",
            password_hash="TEST_ONLY",
            email_verified_at=None,
        )

        db.add_all([customer_a, customer_b, customer_c])
        await db.flush()

        customer_a_id = customer_a.id
        customer_b_id = customer_b.id
        customer_c_id = customer_c.id

        ticket_a = Ticket(
            customer_id=customer_a_id,
            intent="refund",
            status="approved",
            summary="Customer A test ticket",
        )
        ticket_b = Ticket(
            customer_id=customer_b_id,
            intent="refund",
            status="rejected",
            summary="Customer B test ticket",
        )

        db.add_all([ticket_a, ticket_b])
        await db.flush()

        notification_a = Notification(
            event_key=f"api-test:{unique}:customer-a",
            recipient_type="customer",
            customer_id=customer_a_id,
            ticket_id=ticket_a.id,
            event_type="request_approved",
            title="Customer A approval",
            body="Test customer notification A.",
        )
        notification_b = Notification(
            event_key=f"api-test:{unique}:customer-b",
            recipient_type="customer",
            customer_id=customer_b_id,
            ticket_id=ticket_b.id,
            event_type="request_rejected",
            title="Customer B rejection",
            body="Test customer notification B.",
        )
        admin_notification = Notification(
            event_key=f"api-test:{unique}:admin",
            recipient_type="admin",
            customer_id=None,
            ticket_id=ticket_a.id,
            event_type="approval_requested",
            title="Admin approval requested",
            body="Test admin notification.",
        )

        db.add_all([
            notification_a,
            notification_b,
            admin_notification,
        ])
        await db.flush()

        notification_a_id = notification_a.id
        notification_b_id = notification_b.id
        admin_notification_id = admin_notification.id

        await db.commit()

    token_a = create_access_token(customer_a_id)
    token_b = create_access_token(customer_b_id)
    token_c = create_access_token(customer_c_id)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_c = {"Authorization": f"Bearer {token_c}"}
    admin_headers = {
        "X-Admin-Token": main.settings.admin_token
    }

    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:

        # Admin access requires correct authorization.
        response = await client.get("/notifications/admin")
        assert response.status_code == 403

        response = await client.get(
            "/notifications/admin",
            headers={"X-Admin-Token": "invalid"},
        )
        assert response.status_code == 403

        response = await client.get(
            "/notifications/admin",
            headers=headers_a,
        )
        assert response.status_code == 403

        print("Admin authorization: PASS")

        # Customer access requires valid JWT.
        response = await client.get("/notifications/customer")
        assert response.status_code == 401

        response = await client.get(
            "/notifications/customer",
            headers={"Authorization": "Bearer invalid.jwt"},
        )
        assert response.status_code == 401

        print("Customer JWT authorization: PASS")

        # An unverified customer cannot read notifications.
        response = await client.get(
            "/notifications/customer",
            headers=headers_c,
        )
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Email verification required"
        )

        # An unverified customer cannot mark notifications as read.
        response = await client.post(
            f"/notifications/customer/{notification_a_id}/read",
            headers=headers_c,
        )
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Email verification required"
        )

        print("Unverified notification access: BLOCKED")

        # Customer A can only list Customer A's notifications.
        response = await client.get(
            "/notifications/customer",
            headers=headers_a,
        )
        assert response.status_code == 200

        ids_a = {item["id"] for item in response.json()}

        assert notification_a_id in ids_a
        assert notification_b_id not in ids_a
        assert admin_notification_id not in ids_a

        # Customer B has separate notification access.
        response = await client.get(
            "/notifications/customer",
            headers=headers_b,
        )
        assert response.status_code == 200

        ids_b = {item["id"] for item in response.json()}

        assert notification_b_id in ids_b
        assert notification_a_id not in ids_b

        print("Customer notification isolation: PASS")

        # Cross-customer and cross-role writes must fail.
        response = await client.post(
            f"/notifications/customer/{notification_b_id}/read",
            headers=headers_a,
        )
        assert response.status_code == 404

        response = await client.post(
            f"/notifications/customer/{admin_notification_id}/read",
            headers=headers_a,
        )
        assert response.status_code == 404

        response = await client.post(
            f"/notifications/admin/{notification_a_id}/read",
            headers=admin_headers,
        )
        assert response.status_code == 404

        response = await client.post(
            f"/notifications/admin/{admin_notification_id}/read",
        )
        assert response.status_code == 403

        print("Cross-customer and cross-role protection: PASS")

        # Read operation persists and must be idempotent.
        url = f"/notifications/customer/{notification_a_id}/read"

        first = await client.post(url, headers=headers_a)
        assert first.status_code == 200

        first_read_at = first.json()["read_at"]
        assert first_read_at is not None

        second = await client.post(url, headers=headers_a)
        assert second.status_code == 200

        assert second.json()["read_at"] == first_read_at

        async with postgres_session() as db:
            saved = await db.get(Notification, notification_a_id)

            assert saved.read_at is not None

            other = await db.get(Notification, notification_b_id)
            assert other.read_at is None

        print("Customer mark-as-read persistence: PASS")
        print("Repeated read idempotency: PASS")

        # Admin can read only admin notifications.
        response = await client.get(
            "/notifications/admin",
            headers=admin_headers,
        )
        assert response.status_code == 200

        admin_ids = {item["id"] for item in response.json()}

        assert admin_notification_id in admin_ids
        assert notification_a_id not in admin_ids
        assert notification_b_id not in admin_ids

        response = await client.post(
            f"/notifications/admin/{admin_notification_id}/read",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["read_at"] is not None

        print("Admin notification isolation and read: PASS")

    print("NOTIFICATION API SECURITY: PASSED")
