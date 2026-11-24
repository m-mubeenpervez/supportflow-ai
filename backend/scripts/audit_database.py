"""Read-only database topology audit. Never prints credentials or row data."""

import asyncio

from sqlalchemy import text

from app.config import settings
from app.db import engine


async def main() -> None:
    statements = {
        "database": "SELECT current_database()",
        "schema": "SELECT current_schema()",
        "extensions": "SELECT string_agg(extname, ',' ORDER BY extname) FROM pg_extension",
        "public_tables": "SELECT count(*)::text FROM pg_tables WHERE schemaname='public'",
        "application_roles": (
            "SELECT string_agg(rolname, ',' ORDER BY rolname) "
            "FROM pg_roles WHERE rolname NOT LIKE 'pg_%'"
        ),
    }
    try:
        async with engine.connect() as connection:
            for label, statement in statements.items():
                value = await connection.scalar(text(statement))
                print(f"{label}={value or ''}")
            database = await connection.scalar(text("SELECT current_database()"))
            if database != settings.application_database_name:
                raise RuntimeError("Connected database is not authoritative")
            has_vector = await connection.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')"
            ))
            if not has_vector:
                raise RuntimeError("pgvector extension is missing")
            print("authoritative_database_check=PASS")
            print("pgvector_check=PASS")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
