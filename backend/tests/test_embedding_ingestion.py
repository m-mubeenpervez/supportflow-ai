from pathlib import Path
from unittest.mock import patch

import pytest

from backend.embed_policies import main



@pytest.mark.asyncio
async def test_dry_run_no_gemini_calls():
    from unittest.mock import AsyncMock, MagicMock

    fake_result = MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {
            "chunk_id": "TEST-1",
            "policy_id": "TEST",
            "section": "Section",
            "content": "Mock content",
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
        await main(execute=False, limit=2)

    embed.assert_not_called()
    connection.execute.assert_awaited_once()
    fake_engine.begin.assert_not_called()
    fake_engine.dispose.assert_awaited_once()



@pytest.mark.asyncio
async def test_reject_wrong_database():
    with patch(
        "backend.embed_policies.settings.database_url",
        "postgresql+asyncpg://user:password@127.0.0.1:5433/supportflow_db",
    ):
        with pytest.raises(RuntimeError, match="Refusing"):
            await main(execute=False, limit=1)


def test_ingestion_script_exists():
    path = Path("backend/embed_policies.py")
    assert path.exists()


def test_ingestion_script_supports_dry_run():
    content = Path(
        "backend/embed_policies.py"
    ).read_text(encoding="utf-8-sig")

    assert "--execute" in content
    assert "--limit" in content
    assert "embedding IS NULL" in content
