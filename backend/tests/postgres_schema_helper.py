
"""Isolated PostgreSQL schemas for MCP integration tests."""

import asyncio
import re
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from postgres_test_config import get_test_database_url


@asynccontextmanager
async def isolated_postgres_schema():
    """Create and clean up a unique test-only PostgreSQL schema."""

    database_url = get_test_database_url()
    schema = f"sf_test_{uuid.uuid4().hex}"

    if not re.fullmatch(r"sf_test_[a-f0-9]{32}", schema):
        raise RuntimeError("Invalid generated test schema")

    engine = create_async_engine(database_url)

    try:
        async with engine.begin() as connection:
            database = (
                await connection.execute(
                    text("SELECT current_database()")
                )
            ).scalar_one()

            if database != "supportflow_test_db":
                raise RuntimeError("Unsafe database target")

            await connection.execute(
                text(f'CREATE SCHEMA "{schema}"')
            )

        try:
            yield schema
        finally:
            async with engine.begin() as connection:
                database = (
                    await connection.execute(
                        text("SELECT current_database()")
                    )
                ).scalar_one()

                if database != "supportflow_test_db":
                    raise RuntimeError("Unsafe cleanup target")

                await connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )

    finally:
        await engine.dispose()
