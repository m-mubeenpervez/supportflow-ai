
"""Verify PostgreSQL test database fixture."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_postgres_fixture_connection(postgres_session):
    async with postgres_session() as session:
        result = await session.execute(
            text("SELECT current_database()")
        )

        database_name = result.scalar_one()

        assert database_name == "supportflow_test_db"
