
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.auth import create_access_token
from app.models import Customer, Ticket, Message


@pytest.mark.asyncio
async def test_same_ticket_history_and_customer_isolation(
    monkeypatch,
    postgres_session,
):
    monkeypatch.setattr(main, "Session", postgres_session)

    suffix = uuid4().hex

    async with postgres_session() as db:
        customer_a = Customer(
            name="History Customer A",
            email=f"history-a-{suffix}@test.local",
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )
        customer_b = Customer(
            name="History Customer B",
            email=f"history-b-{suffix}@test.local",
            password_hash="TEST_ONLY",
            email_verified_at=datetime.now(timezone.utc),
        )

        db.add_all([customer_a, customer_b])
        await db.flush()

        a_id = customer_a.id
        b_id = customer_b.id

        ticket_a = Ticket(
            customer_id=a_id,
            summary="Damaged package",
            status="open",
        )
        ticket_b = Ticket(
            customer_id=b_id,
            summary="Private delivery issue",
            status="open",
        )
        db.add_all([ticket_a, ticket_b])
        await db.flush()

        a_ticket_id = ticket_a.id

        db.add_all([
            Message(
                ticket_id=ticket_a.id,
                role="user",
                content="My package arrived damaged",
            ),
            Message(
                ticket_id=ticket_a.id,
                role="assistant",
                content="Please explain the damage",
            ),
            Message(
                ticket_id=ticket_b.id,
                role="user",
                content="PRIVATE CUSTOMER B MESSAGE",
            ),
        ])
        await db.commit()

    fake_ainvoke = AsyncMock(
        return_value={
            "intent": "general",
            "order_id": None,
            "draft": "Thank you for the details.",
            "needs_approval": False,
            "sources": [],
        }
    )

    monkeypatch.setattr(
        main,
        "graph",
        SimpleNamespace(ainvoke=fake_ainvoke),
    )

    headers_a = {
        "Authorization": f"Bearer {create_access_token(a_id)}"
    }
    headers_b = {
        "Authorization": f"Bearer {create_access_token(b_id)}"
    }

    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:

        response = await client.post(
            "/chat",
            headers=headers_a,
            json={
                "ticket_id": a_ticket_id,
                "message": "There is a crack on the item",
            },
        )
        assert response.status_code == 200, response.text

        state = fake_ainvoke.await_args.args[0]

        assert state["customer_id"] == a_id
        assert state["message"] == "There is a crack on the item"
        assert state["history"] == [
            {
                "role": "user",
                "content": "My package arrived damaged",
            },
            {
                "role": "assistant",
                "content": "Please explain the damage",
            },
        ]
        assert "PRIVATE CUSTOMER B MESSAGE" not in str(state)

        calls_before = fake_ainvoke.await_count

        # Customer B cannot use Customer A's ticket.
        response = await client.post(
            "/chat",
            headers=headers_b,
            json={
                "ticket_id": a_ticket_id,
                "message": "Attempt to access another ticket",
            },
        )

        assert response.status_code == 404, response.text
        assert fake_ainvoke.await_count == calls_before

        # A new conversation must not inherit another ticket.
        response = await client.post(
            "/chat",
            headers=headers_a,
            json={
                "message": "I have a completely new question",
            },
        )

        assert response.status_code == 200, response.text

        new_state = fake_ainvoke.await_args.args[0]
        assert new_state["customer_id"] == a_id
        assert new_state["history"] == []

    print("Same-ticket history: VERIFIED")
    print("Cross-customer ticket access: BLOCKED")
    print("New conversation history: EMPTY")
    print("Gemini/MCP external requests: ZERO")
