
"""Shared PostgreSQL test fixtures."""

import os
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

# The suite covers both legacy-token and JWT admin components. API regression
# tests use the explicit legacy mode; JWT/RBAC tests exercise their modules
# directly with isolated applications and fixtures.
os.environ["ADMIN_JWT_ROUTES_ENABLED"] = "false"

from app.db import Base
from postgres_test_config import get_test_database_url


@pytest.fixture
async def postgres_session():
    """Provide a transaction-scoped session in a temporary test schema."""
    import uuid

    from sqlalchemy import text
    import app.models  # Register all models before create_all.

    database_url = get_test_database_url()
    parsed_url = make_url(database_url)

    if (
        parsed_url.drivername != "postgresql+asyncpg"
        or parsed_url.database != "supportflow_test_db"
    ):
        raise RuntimeError("Unsafe PostgreSQL test database.")

    schema = "sf_legacy_test_" + uuid.uuid4().hex[:16]

    admin_engine = create_async_engine(database_url)
    engine = None
    schema_created = False

    try:
        # Create only this test's unique schema.
        async with admin_engine.begin() as admin:
            actual = await admin.scalar(
                text("SELECT current_database()")
            )
            if actual != "supportflow_test_db":
                raise RuntimeError("Connected to wrong database.")

            await admin.execute(
                text(f'CREATE SCHEMA "{schema}"')
            )
            schema_created = True

        # Force all unqualified application tables into the test schema.
        engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={
                "server_settings": {
                    "search_path": schema,
                },
            },
        )

        async with engine.begin() as conn:
            actual_schema = await conn.scalar(
                text("SELECT current_schema()")
            )
            if actual_schema != schema:
                raise RuntimeError("Test schema selection failed.")

            await conn.run_sync(Base.metadata.create_all)

        # Preserve the original shared-transaction/savepoint behavior.
        async with engine.connect() as connection:
            transaction = await connection.begin()

            TestSession = async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            try:
                yield TestSession
            finally:
                if transaction.is_active:
                    await transaction.rollback()

    finally:
        if engine is not None:
            await engine.dispose()

        if schema_created:
            if not schema.startswith("sf_legacy_test_"):
                raise RuntimeError("Unsafe test cleanup.")

            async with admin_engine.begin() as admin:
                actual = await admin.scalar(
                    text("SELECT current_database()")
                )
                if actual != "supportflow_test_db":
                    raise RuntimeError("Cleanup database mismatch.")

                await admin.execute(
                    text(f'DROP SCHEMA "{schema}" CASCADE')
                )

        await admin_engine.dispose()
