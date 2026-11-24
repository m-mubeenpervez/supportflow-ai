
"""Verify PostgreSQL database configuration in a subprocess."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from postgres_test_config import get_test_database_url


def test_database_environment_override():
    """A fresh process must use the isolated PostgreSQL test DB."""

    test_database_url = get_test_database_url()

    env = os.environ.copy()
    env["DATABASE_URL"] = test_database_url
    env["GEMINI_API_KEY"] = ""

    code = """
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import engine

expected_database = "supportflow_test_db"

settings_url = make_url(settings.database_url)
engine_url = engine.url

assert settings_url.drivername == "postgresql+asyncpg"
assert engine_url.drivername == "postgresql+asyncpg"

assert settings_url.database == expected_database
assert engine_url.database == expected_database

assert engine_url.host == settings_url.host
assert engine_url.port == settings_url.port
assert engine_url.username == settings_url.username

print("ISOLATED_POSTGRES_DATABASE_OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, (
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )

    assert "ISOLATED_POSTGRES_DATABASE_OK" in result.stdout
