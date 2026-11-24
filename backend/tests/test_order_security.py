
"""Order ownership security tests using PostgreSQL."""

import pytest

from app import tools
from app.models import Customer, Order


@pytest.mark.asyncio
async def test_order_ownership(
    monkeypatch,
    postgres_session,
):
    """Only the order owner can retrieve its details."""

    # Use isolated PostgreSQL test session.
    monkeypatch.setattr(
        tools,
        "Session",
        postgres_session,
    )

    async with postgres_session() as db:
        customer_a = Customer(
            name="Customer A",
            email="customer-a@test.local",
        )

        customer_b = Customer(
            name="Customer B",
            email="customer-b@test.local",
        )

        db.add_all([customer_a, customer_b])
        await db.flush()

        customer_a_id = customer_a.id
        customer_b_id = customer_b.id

        db.add(
            Order(
                id="ORD9999",
                customer_id=customer_a_id,
                item="Test Headphones",
                status="shipped",
                total=4999,
            )
        )

        await db.commit()

    # 1. Owner can access their order.
    owner_result = await tools.get_order_details(
        customer_a_id,
        "ORD9999",
    )

    assert owner_result["id"] == "ORD9999"
    assert owner_result["item"] == "Test Headphones"

    # 2. Another customer cannot access this order.
    unauthorized_result = await tools.get_order_details(
        customer_b_id,
        "ORD9999",
    )

    assert "error" in unauthorized_result
    assert "item" not in unauthorized_result
    assert "total" not in unauthorized_result

    # 3. Nonexistent order must not expose data.
    missing_result = await tools.get_order_details(
        customer_a_id,
        "ORD0000",
    )

    assert "error" in missing_result
