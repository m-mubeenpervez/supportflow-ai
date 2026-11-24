from unittest.mock import AsyncMock

import pytest

from app import mcp_server, semantic_search


@pytest.mark.asyncio
async def test_semantic_success(monkeypatch):
    monkeypatch.setattr(
        mcp_server.settings,
        "gemini_api_key",
        "TEST_ONLY_KEY",
    )

    semantic = AsyncMock(
        return_value=[{"text": "Semantic policy result"}]
    )

    monkeypatch.setattr(
        mcp_server, "semantic_search", semantic
    )

    monkeypatch.setattr(
        mcp_server,
        "search_policies",
        lambda query: pytest.fail(
            "Lexical fallback should not run."
        ),
    )

    result = await mcp_server.knowledge_search(
        query="refund policy"
    )

    assert result == [{"text": "Semantic policy result"}]
    semantic.assert_awaited_once_with(
        "refund policy", top_k=3
    )


@pytest.mark.asyncio
async def test_semantic_failure_uses_lexical(monkeypatch):
    monkeypatch.setattr(
        mcp_server.settings,
        "gemini_api_key",
        "TEST_ONLY_KEY",
    )

    monkeypatch.setattr(
        mcp_server,
        "semantic_search",
        AsyncMock(side_effect=RuntimeError("Vector unavailable")),
    )

    monkeypatch.setattr(
        mcp_server,
        "search_policies",
        lambda query: [{"text": "Safe lexical policy"}],
    )

    result = await mcp_server.knowledge_search(
        query="refund policy"
    )

    assert result == [{"text": "Safe lexical policy"}]


@pytest.mark.asyncio
async def test_empty_semantic_results_use_lexical(monkeypatch):
    monkeypatch.setattr(
        mcp_server.settings,
        "gemini_api_key",
        "TEST_ONLY_KEY",
    )

    monkeypatch.setattr(
        mcp_server,
        "semantic_search",
        AsyncMock(return_value=[]),
    )

    monkeypatch.setattr(
        mcp_server,
        "search_policies",
        lambda query: [{"text": "Lexical result"}],
    )

    result = await mcp_server.knowledge_search(
        query="delivery policy"
    )

    assert result == [{"text": "Lexical result"}]


@pytest.mark.asyncio
async def test_without_gemini_uses_lexical(monkeypatch):
    monkeypatch.setattr(
        mcp_server.settings,
        "gemini_api_key",
        "",
    )

    semantic = AsyncMock()
    monkeypatch.setattr(
        mcp_server, "semantic_search", semantic
    )

    monkeypatch.setattr(
        mcp_server,
        "search_policies",
        lambda query: [{"text": "Local policy"}],
    )

    result = await mcp_server.knowledge_search(
        query="general policy"
    )

    assert result == [{"text": "Local policy"}]
    semantic.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_query_rejected(monkeypatch):
    monkeypatch.setattr(
        mcp_server.settings,
        "gemini_api_key",
        "",
    )

    with pytest.raises(ValueError):
        await mcp_server.knowledge_search(query="   ")


def test_semantic_uses_shared_engine():
    source = (
        semantic_search.__file__
        and open(
            semantic_search.__file__,
            encoding="utf-8-sig",
        ).read()
    )

    assert "from .db import engine" in source
    assert "async with engine.connect()" in source
    assert "urlsplit(" not in source
