
"""Verify PostgreSQL test schema creation and cleanup."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from postgres_schema_helper import isolated_postgres_schema
from postgres_test_config import get_test_database_url


@pytest.mark.asyncio
async def test_postgres_schema_isolation():
    engine = create_async_engine(get_test_database_url())

    try:
        async with isolated_postgres_schema() as schema:
            assert schema.startswith("sf_test_")

            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_namespace "
                        "WHERE nspname = :schema)"
                    ),
                    {"schema": schema},
                )

                assert result.scalar_one() is True

        # Schema should no longer exist after cleanup.
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_namespace "
                    "WHERE nspname = :schema)"
                ),
                {"schema": schema},
            )

            assert result.scalar_one() is False

    finally:
        await engine.dispose()
