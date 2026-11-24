"""Human approval API tests using isolated PostgreSQL."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app import main
from app.models import Customer, Ticket, Audit
from app.auth import hash_password


@pytest.mark.asyncio
async def test_approval_api_security(
    monkeypatch,
    postgres_session,
):
    monkeypatch.setattr(
        main,
        "Session",
        postgres_session,
    )

    assert main.settings.admin_token, (
        "Test requires a configured admin token."
    )

    # Test records exist only inside isolated test transaction.
    async with postgres_session() as db:
        customer = Customer(
            name="Approval Test Customer",
            email="approval-test@test.local",
            password_hash=hash_password("TestPassword123!"),
        )

        db.add(customer)
        await db.flush()

        refund_ticket = Ticket(
            customer_id=customer.id,
            intent="refund",
            status="pending_approval",
            summary="Damaged item refund request",
        )

        cancel_ticket = Ticket(
            customer_id=customer.id,
            intent="cancel",
            status="pending_approval",
            summary="Cancellation request",
        )

        db.add_all([refund_ticket, cancel_ticket])
        await db.flush()

        refund_id = refund_ticket.id
        cancel_id = cancel_ticket.id

        await db.commit()

    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:

        refund_url = f"/tickets/{refund_id}/decision"
        cancel_url = f"/tickets/{cancel_id}/decision"

        admin_headers = {
            "X-Admin-Token": main.settings.admin_token
        }

        # 1. Unauthorized request must fail.
        response = await client.post(
            refund_url,
            json={"approve": True},
        )

        assert response.status_code == 403
        print("TEST 1 - Unauthorized approval rejected: PASS")

        # 2. Authorized approval succeeds.
        response = await client.post(
            refund_url,
            json={
                "approve": True,
                "note": "Evidence reviewed",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        print("TEST 2 - Authorized approval: PASS")

        # 3. Duplicate approval must fail.
        response = await client.post(
            refund_url,
            json={"approve": True},
            headers=admin_headers,
        )

        assert response.status_code == 409

        print("TEST 3 - Duplicate approval rejected: PASS")

        # 4. Authorized rejection succeeds.
        response = await client.post(
            cancel_url,
            json={
                "approve": False,
                "note": "Request not eligible",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

        print("TEST 4 - Authorized rejection: PASS")

        # 5. Rejected decision cannot be changed.
        response = await client.post(
            cancel_url,
            json={"approve": True},
            headers=admin_headers,
        )

        assert response.status_code == 409

        print("TEST 5 - Rejected ticket protected: PASS")

    # 6. Verify statuses and audit records.
    async with postgres_session() as db:
        refund = await db.get(Ticket, refund_id)
        cancellation = await db.get(Ticket, cancel_id)

        assert refund.status == "approved"
        assert refund.approved is True

        assert cancellation.status == "rejected"
        assert cancellation.approved is False

        audits = (
            await db.scalars(
                select(Audit).where(
                    Audit.ticket_id.in_(
                        [refund_id, cancel_id]
                    )
                )
            )
        ).all()

        assert len(audits) == 2

        actions = sorted(audit.action for audit in audits)

        assert actions == ["approved", "rejected"]

        print("TEST 6 - Database statuses and audit logs: PASS")

    print("\nAPPROVAL API SECURITY: PASSED")
