import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.embed_policies import main


class FakeConnection:
    def __init__(self):
        self.saved = []

    async def execute(self, statement, parameters=None):
        sql = str(statement)

        if "SELECT chunk_id" in sql:
            rows = [{
                "chunk_id": "SF-TEST-001",
                "policy_id": "SF-TEST",
                "section": "Test Section",
                "content": "Refunds require human approval.",
            }]

            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(
                    all=lambda: rows
                )
            )

        if "UPDATE policy_chunks" in sql:
            self.saved.append(parameters)
            return SimpleNamespace(rowcount=1)

        raise AssertionError("Unexpected SQL statement")


class FakeContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()
        self.dispose = AsyncMock()

    def connect(self):
        return FakeContext(self.connection)

    def begin(self):
        return FakeContext(self.connection)


@pytest.mark.asyncio
async def test_successful_embedding_storage():
    fake_engine = FakeEngine()
    fake_embedding = AsyncMock(
        return_value=[0.1] * 768
    )

    with patch(
        "backend.embed_policies.engine",
        fake_engine,
    ), patch(
        "backend.embed_policies.embed_document",
        fake_embedding,
    ):
        await main(execute=True, limit=1)

    fake_embedding.assert_awaited_once()

    assert len(fake_engine.connection.saved) == 1

    saved = fake_engine.connection.saved[0]

    assert saved["chunk_id"] == "SF-TEST-001"

    vector = json.loads(saved["embedding"])

    assert len(vector) == 768
    assert vector == [0.1] * 768

    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_pending_chunks_skips_api():
    fake_engine = FakeEngine()

    original_execute = fake_engine.connection.execute

    async def empty_select(statement, parameters=None):
        if "SELECT chunk_id" in str(statement):
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(
                    all=lambda: []
                )
            )

        return await original_execute(statement, parameters)

    fake_engine.connection.execute = empty_select

    with patch(
        "backend.embed_policies.engine",
        fake_engine,
    ), patch(
        "backend.embed_policies.embed_document",
        new_callable=AsyncMock,
    ) as mocked_embed:
        await main(execute=True, limit=1)

    mocked_embed.assert_not_awaited()
    assert fake_engine.connection.saved == []
    fake_engine.dispose.assert_awaited_once()
