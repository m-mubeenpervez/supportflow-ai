
"""Database engine and session configuration."""

import os
import re

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


def get_engine_options() -> dict:
    """Configure isolated PostgreSQL schemas for test subprocesses."""

    schema = os.environ.get("TEST_DB_SCHEMA")

    if not schema:
        return {}

    # Test schema names must contain safe SQL identifier characters.
    if not re.fullmatch(r"sf_test_[a-z0-9_]+", schema):
        raise RuntimeError("Invalid test database schema name")

    database_url = make_url(settings.database_url)

    if (
        database_url.drivername != "postgresql+asyncpg"
        or database_url.database != "supportflow_test_db"
    ):
        raise RuntimeError(
            "TEST_DB_SCHEMA requires supportflow_test_db"
        )

    return {
        "connect_args": {
            "server_settings": {
                "search_path": schema,
            }
        }
    }


engine = create_async_engine(
    settings.database_url,
    **get_engine_options(),
)

Session = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db():
    from . import models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
