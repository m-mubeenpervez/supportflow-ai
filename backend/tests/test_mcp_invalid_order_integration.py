
"""MCP and LangGraph integration tests using isolated PostgreSQL."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from postgres_schema_helper import isolated_postgres_schema
from postgres_test_config import get_test_database_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def run_isolated_graph_test(code: str):
    """Run graph and MCP operations in an isolated PostgreSQL schema."""

    async with isolated_postgres_schema() as schema:
        env = os.environ.copy()
        env["DATABASE_URL"] = get_test_database_url()
        env["TEST_DB_SCHEMA"] = schema
        env["GEMINI_API_KEY"] = ""

        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-c", code],
            env=env,
            cwd=str(BACKEND_ROOT),
            capture_output=True,
            text=True,
            timeout=45,
        )

        assert result.returncode == 0, (
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )


@pytest.mark.asyncio
async def test_real_mcp_rejects_invalid_order():
    code = """
import asyncio

from app.db import init_db
from app.mcp_client import call_business_tool
from app.mcp_parser import parse_mcp_result


async def main():
    await init_db()

    result = await call_business_tool(
        tool_name="order_details",
        arguments={"order_id": "ORD999999999"},
        authenticated_customer_id=1,
    )

    order = parse_mcp_result(result)

    assert isinstance(order, dict)
    assert order == {
        "error": "Order not found or access denied"
    }


asyncio.run(main())
"""

    await run_isolated_graph_test(code)


@pytest.mark.asyncio
async def test_complete_graph_rejects_invalid_order():
    code = """
import asyncio

from app.db import init_db
from app.graph import graph


async def main():
    await init_db()

    result = await graph.ainvoke({
        "message": "Refund my order ORD999999999",
        "customer_id": 1,
    })

    assert result["intent"] == "refund"
    assert result["order_id"] == "ORD999999999"
    assert result["order"] == {
        "error": "Order not found or access denied"
    }
    assert result["needs_approval"] is False
    assert result["draft"] == (
        "I could not verify that order for your account. "
        "Please check the order ID."
    )


asyncio.run(main())
"""

    await run_isolated_graph_test(code)


@pytest.mark.asyncio
async def test_complete_graph_retrieves_valid_order():
    code = """
import asyncio

from app.db import init_db, Session
from app.models import Customer, Order
from app.graph import graph


async def main():
    await init_db()

    async with Session() as db:
        customer = Customer(
            name="Test Customer",
            email="valid-order@test.local",
        )

        db.add(customer)
        await db.flush()

        customer_id = customer.id

        order = Order(
            id="ORD1023",
            customer_id=customer_id,
            item="Wireless Headphones",
            status="delivered",
            total=5000,
        )

        db.add(order)
        await db.commit()

    result = await graph.ainvoke({
        "message": "Where is my order ORD1023?",
        "customer_id": customer_id,
    })

    assert result["intent"] == "delivery"
    assert result["order_id"] == "ORD1023"

    assert result["order"]["id"] == "ORD1023"
    assert result["order"]["status"] == "delivered"
    assert result["order"]["item"] == "Wireless Headphones"

    assert isinstance(result["sources"], list)
    assert result["needs_approval"] is False

    assert result["draft"] == (
        "Your order status is: delivered. "
        "Our team can investigate further if needed."
    )


asyncio.run(main())
"""

    await run_isolated_graph_test(code)


@pytest.mark.asyncio
async def test_complete_graph_blocks_cross_customer_order():
    code = """
import asyncio

from app.db import init_db, Session
from app.models import Customer, Order
from app.graph import graph


async def main():
    await init_db()

    async with Session() as db:
        customer_a = Customer(
            name="Customer A",
            email="customer-a@security.test",
        )

        customer_b = Customer(
            name="Customer B",
            email="customer-b@security.test",
        )

        db.add_all([customer_a, customer_b])
        await db.flush()

        customer_a_id = customer_a.id
        customer_b_id = customer_b.id

        db.add(
            Order(
                id="ORD1023",
                customer_id=customer_a_id,
                item="Wireless Headphones",
                status="delivered",
                total=5000,
            )
        )

        await db.commit()

    result = await graph.ainvoke({
        "message": "Where is my order ORD1023?",
        "customer_id": customer_b_id,
    })

    assert result["intent"] == "delivery"
    assert result["order_id"] == "ORD1023"

    assert result["order"] == {
        "error": "Order not found or access denied"
    }

    assert result["needs_approval"] is False
    assert result["draft"] == (
        "I could not verify that order for your account. "
        "Please check the order ID."
    )

    assert "Wireless Headphones" not in result["draft"]
    assert "delivered" not in result["draft"]


asyncio.run(main())
"""

    await run_isolated_graph_test(code)
