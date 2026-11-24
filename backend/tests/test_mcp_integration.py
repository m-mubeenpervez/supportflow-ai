
"""Real MCP integration tests using isolated PostgreSQL schemas."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from postgres_schema_helper import isolated_postgres_schema
from postgres_test_config import get_test_database_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def run_isolated_mcp_test(code: str):
    """Execute real MCP calls against an isolated test schema."""

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
async def test_real_mcp_knowledge_search():
    """Verify actual MCP knowledge-search communication."""

    code = """
import asyncio

from app.db import init_db
from app.mcp_client import call_business_tool


async def main():
    await init_db()

    result = await call_business_tool(
        tool_name="knowledge_search",
        arguments={"query": "refund policy"},
        authenticated_customer_id=1,
    )

    assert result.isError is False
    assert len(result.content) > 0

    text_blocks = [
        block.text
        for block in result.content
        if block.type == "text"
    ]

    assert text_blocks
    assert any(text.strip() for text in text_blocks)


asyncio.run(main())
"""

    await run_isolated_mcp_test(code)


@pytest.mark.asyncio
async def test_real_mcp_cross_customer_order_denied():
    """MCP must not expose another customer's order."""

    code = """
import asyncio

from app.db import init_db, Session
from app.models import Customer, Order
from app.mcp_client import call_business_tool
from app.mcp_parser import parse_mcp_result


async def main():
    await init_db()

    async with Session() as db:
        customer_a = Customer(
            name="Customer A",
            email="mcp-a@security.test",
        )

        customer_b = Customer(
            name="Customer B",
            email="mcp-b@security.test",
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

    result = await call_business_tool(
        tool_name="order_details",
        arguments={"order_id": "ORD1023"},
        authenticated_customer_id=customer_b_id,
    )

    assert result.isError is False

    data = parse_mcp_result(result)

    assert isinstance(data, dict)
    assert data.get("error") == (
        "Order not found or access denied"
    )

    assert "item" not in data
    assert "total" not in data


asyncio.run(main())
"""

    await run_isolated_mcp_test(code)
