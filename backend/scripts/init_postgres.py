
"""Initialize SupportFlow AI PostgreSQL database tables."""

import asyncio

from app.db import Base, init_db


async def main():
    await init_db()

    print("POSTGRES_TABLES_INITIALIZED")
    print("Tables:")

    for table in Base.metadata.sorted_tables:
        print(f"- {table.name}")


if __name__ == "__main__":
    asyncio.run(main())
