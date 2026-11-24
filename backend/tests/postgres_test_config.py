
"""Safe PostgreSQL configuration for automated tests."""

from sqlalchemy.engine import make_url

from app.config import settings


TEST_DATABASE_NAME = "supportflow_test_db"


def get_test_database_url() -> str:
    """Build and validate the isolated PostgreSQL test URL."""

    development_url = make_url(settings.database_url)

    if development_url.drivername != "postgresql+asyncpg":
        raise RuntimeError(
            "Tests require the postgresql+asyncpg driver."
        )

    if development_url.database not in ("supportflow_db", "supportflow_recovery"):
        raise RuntimeError(
            "Unexpected development database configuration."
        )

    test_url = development_url.set(
        database=TEST_DATABASE_NAME
    )

    if test_url.database != TEST_DATABASE_NAME:
        raise RuntimeError(
            "Unsafe test database configuration."
        )

    return test_url.render_as_string(
        hide_password=False
    )
