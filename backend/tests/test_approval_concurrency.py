"""Concurrent approval test in an isolated PostgreSQL schema."""

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app import main
from app.models import Audit, Customer, Ticket
from postgres_test_config import get_test_database_url
from test_email_worker_integration import worker_database


@pytest.mark.asyncio
async def test_concurrent_admin_decisions(
    monkeypatch,
    worker_database,
):
    database_url = get_test_database_url()
    parsed = make_url(database_url)

    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.database != "supportflow_test_db"
        or parsed.host not in {"127.0.0.1", "localhost"}
    ):
        raise RuntimeError("Unsafe test database target")

    assert main.settings.admin_token

    # Each request gets an independent session and transaction.
    # The fixture creates and cleans up a dedicated temporary schema.
    TestSession = worker_database

    monkeypatch.setattr(main, "Session", TestSession)

    async with TestSession() as db:
        async with db.begin():
            customer = Customer(
                name="Concurrent Approval Test",
                email=f"concurrent-{uuid4().hex}@test.local",
                password_hash="test-only-not-for-login",
            )
            db.add(customer)
            await db.flush()

            ticket = Ticket(
                customer_id=customer.id,
                intent="refund",
                status="pending_approval",
                summary="Concurrent approval test",
            )
            db.add(ticket)
            await db.flush()
            ticket_id = ticket.id

    headers = {
        "X-Admin-Token": main.settings.admin_token
    }
    url_path = f"/tickets/{ticket_id}/decision"

    async def submit(approve):
        transport = ASGITransport(app=main.app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(
                url_path,
                json={
                    "approve": approve,
                    "note": "Concurrent test",
                },
                headers=headers,
            )

    responses = await asyncio.gather(
        submit(True),
        submit(False),
    )

    statuses = sorted(
        response.status_code for response in responses
    )

    print("=== CONCURRENT APPROVAL TEST ===")
    print("HTTP statuses:", statuses)

    assert statuses == [200, 409]

    async with TestSession() as db:
        ticket = await db.get(Ticket, ticket_id)
        assert ticket is not None

        audits = (
            await db.scalars(
                select(Audit).where(
                    Audit.ticket_id == ticket_id
                )
            )
        ).all()

        print("Final ticket status:", ticket.status)
        print("Audit records:", len(audits))

        assert ticket.status in ("approved", "rejected")
        assert len(audits) == 1
        assert audits[0].action == ticket.status

    print("Concurrent decisions: PASSED")
    print("Duplicate audit prevention: PASSED")
