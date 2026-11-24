
"""Chat authentication and ownership security tests using PostgreSQL."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.auth import create_access_token, hash_password
from app.models import Customer, Ticket


@pytest.mark.asyncio
async def test_chat_authentication_and_ownership(
    monkeypatch,
    postgres_session,
):
    # Use isolated PostgreSQL test database.
    monkeypatch.setattr(
        main,
        "Session",
        postgres_session,
    )

    # Create two test customers and one ticket.
    async with postgres_session() as db:
        customer_a = Customer(
            name="Customer A",
            email="a@test.local",
            password_hash=hash_password("Password12345!"),
            email_verified_at=datetime.now(timezone.utc),
        )

        customer_b = Customer(
            name="Customer B",
            email="b@test.local",
            password_hash=hash_password("Password12345!"),
            email_verified_at=datetime.now(timezone.utc),
        )

        customer_c = Customer(
            name="Customer C",
            email="c@test.local",
            password_hash=hash_password("Password12345!"),
            email_verified_at=None,
        )

        db.add_all([customer_a, customer_b, customer_c])
        await db.flush()

        a_id = customer_a.id
        b_id = customer_b.id
        c_id = customer_c.id

        ticket = Ticket(
            customer_id=a_id,
            summary="Existing support request",
        )

        db.add(ticket)
        await db.flush()

        ticket_id = ticket.id
        await db.commit()

    # Mock the AI graph to avoid real Gemini API calls.
    mock_graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "intent": "general",
                "order_id": None,
                "draft": "How can we help?",
                "needs_approval": False,
                "sources": [],
            }
        )
    )

    monkeypatch.setattr(
        main,
        "graph",
        mock_graph,
    )

    transport = ASGITransport(app=main.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:

        # 1. Missing JWT must be rejected.
        response = await client.post(
            "/chat",
            json={"message": "Hello support"},
        )

        assert response.status_code == 401

        # 2. Invalid JWT must be rejected.
        response = await client.post(
            "/chat",
            json={"message": "Hello support"},
            headers={
                "Authorization": "Bearer invalid-token"
            },
        )

        assert response.status_code == 401

        # 3. Unverified customer must be blocked,
        # even with a valid JWT.
        token_c = create_access_token(c_id)

        response = await client.post(
            "/chat",
            json={"message": "Hello support"},
            headers={
                "Authorization": f"Bearer {token_c}"
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Email verification required"
        )
        mock_graph.ainvoke.assert_not_awaited()

        # 4. Valid verified customer JWT must work.
        token_a = create_access_token(a_id)

        response = await client.post(
            "/chat",
            json={"message": "Hello support"},
            headers={
                "Authorization": f"Bearer {token_a}"
            },
        )

        assert response.status_code == 200
        assert response.json()["reply"] == "How can we help?"

        # Verify graph received authenticated identity.
        assert (
            mock_graph.ainvoke.call_args.args[0]["customer_id"]
            == a_id
        )

        # 5. Verified Customer B cannot access Customer A's ticket.
        token_b = create_access_token(b_id)

        mock_graph.ainvoke.reset_mock()

        response = await client.post(
            "/chat",
            json={
                "message": "Update my ticket",
                "ticket_id": ticket_id,
            },
            headers={
                "Authorization": f"Bearer {token_b}"
            },
        )

        assert response.status_code == 404
        mock_graph.ainvoke.assert_not_awaited()
