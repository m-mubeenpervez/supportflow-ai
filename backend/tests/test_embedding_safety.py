from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from backend.app.db import engine
from backend.embed_policies import main


async def get_embedding_counts():
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(embedding) AS embedded
            FROM policy_chunks
        """))

        return tuple(result.one())


@pytest.fixture(autouse=True)
async def cleanup_database_connections():
    # Ensure no connection from a previous test loop is reused.
    await engine.dispose()

    yield

    # Dispose connections before pytest closes the event loop.
    await engine.dispose()



@pytest.mark.asyncio
async def test_api_failure_preserves_database():
    from unittest.mock import MagicMock

    pending = {
        "chunk_id": "SF-TEST-001",
        "policy_id": "SF-TEST",
        "section": "Test Section",
        "content": "Test policy content",
    }

    result = MagicMock()
    result.mappings.return_value.all.return_value = [pending]

    connection = AsyncMock()
    connection.execute.return_value = result

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__aenter__ = AsyncMock(
        return_value=connection
    )
    fake_engine.connect.return_value.__aexit__ = AsyncMock(
        return_value=False
    )
    fake_engine.dispose = AsyncMock()

    fake_embed = AsyncMock(
        side_effect=RuntimeError("Simulated Gemini API failure")
    )

    with (
        patch("backend.embed_policies.engine", fake_engine),
        patch(
            "backend.embed_policies.settings.database_url",
                "postgresql+asyncpg://test:test@127.0.0.1:5432/supportflow_test_db",
        ),
        patch(
            "backend.embed_policies.settings.application_database_name",
            "supportflow_test_db",
        ),
        patch("backend.embed_policies.embed_document", fake_embed),
    ):
        with pytest.raises(
            RuntimeError, match="Simulated Gemini API failure"
        ):
            await main(execute=True, limit=1)

    fake_embed.assert_awaited_once()
    connection.execute.assert_awaited_once()
    fake_engine.begin.assert_not_called()
    fake_engine.dispose.assert_awaited_once()



@pytest.mark.asyncio
async def test_dry_run_preserves_database():
    """Assert dry run performs no writes using a fake database."""

    from unittest.mock import MagicMock

    fake_result = MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {
            "chunk_id": "TEST-2",
            "policy_id": "TEST",
            "section": "Mock",
            "content": "Fake pending chunk",
        }
    ]

    connection = AsyncMock()
    connection.execute.return_value = fake_result

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__aenter__ = AsyncMock(
        return_value=connection
    )
    fake_engine.connect.return_value.__aexit__ = AsyncMock(
        return_value=False
    )
    fake_engine.dispose = AsyncMock()

    with (
        patch("backend.embed_policies.engine", fake_engine),
        patch(
            "backend.embed_policies.settings.database_url",
                "postgresql+asyncpg://test:test@127.0.0.1:5432/supportflow_test_db",
        ),
        patch(
            "backend.embed_policies.settings.application_database_name",
            "supportflow_test_db",
        ),
        patch("backend.embed_policies.embed_document") as embed,
    ):
        await main(execute=False, limit=3)

    connection.execute.assert_awaited_once()
    embed.assert_not_called()
    fake_engine.begin.assert_not_called()
    fake_engine.dispose.assert_awaited_once()
