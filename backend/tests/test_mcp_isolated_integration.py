
"""Verify MCP reads from an isolated PostgreSQL schema."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from postgres_schema_helper import isolated_postgres_schema
from postgres_test_config import get_test_database_url


def test_mcp_uses_isolated_database():
    """Verify MCP subprocess reads isolated PostgreSQL data."""

    async def run_test():
        async with isolated_postgres_schema() as schema:
            env = os.environ.copy()

            env["DATABASE_URL"] = get_test_database_url()
            env["TEST_DB_SCHEMA"] = schema
            env["GEMINI_API_KEY"] = ""

            code = """
import asyncio

from sqlalchemy import text

from app.config import settings
from app.db import Session, engine, init_db
from app.models import Customer, Order
from app.mcp_client import call_business_tool
from app.mcp_parser import parse_mcp_result


async def main():
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT current_database(), current_schema()")
        )

        database, schema = result.one()

        assert database == "supportflow_test_db"
        assert schema.startswith("sf_test_")

    await init_db()

    async with Session() as db:
        customer = Customer(
            name="Isolated Test Customer",
            email="isolated@test.local",
        )

        db.add(customer)
        await db.flush()

        customer_id = customer.id

        order = Order(
            id="ORD9999",
            customer_id=customer_id,
            item="Test Keyboard",
            status="shipped",
            total=2500,
        )

        db.add(order)
        await db.commit()

    result = await call_business_tool(
        tool_name="order_details",
        arguments={"order_id": "ORD9999"},
        authenticated_customer_id=customer_id,
    )

    data = parse_mcp_result(result)

    assert data["id"] == "ORD9999"
    assert data["item"] == "Test Keyboard"
    assert data["status"] == "shipped"

    print("ISOLATED_POSTGRES_MCP_OK")


asyncio.run(main())
"""

            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-c", code],
                env=env,
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                timeout=45,
            )

            assert result.returncode == 0, (
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )

            assert "ISOLATED_POSTGRES_MCP_OK" in result.stdout

    asyncio.run(run_test())
