import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.embeddings import (
    validate_embedding,
    prepare_document,
    prepare_query,
    embed_text,
)


def test_valid_embedding():
    vector = validate_embedding([0.1] * 768)
    assert len(vector) == 768


def test_incorrect_dimensions():
    with pytest.raises(ValueError, match="Expected 768"):
        validate_embedding([0.1] * 100)


def test_invalid_numbers():
    for invalid in [math.nan, math.inf, -math.inf]:
        with pytest.raises(ValueError, match="invalid numbers"):
            validate_embedding([invalid] * 768)


def test_empty_document():
    with pytest.raises(ValueError, match="empty"):
        prepare_document("   ", "Refund Policy")


def test_empty_query():
    with pytest.raises(ValueError, match="empty"):
        prepare_query("   ")


@pytest.mark.asyncio
async def test_mocked_gemini_embedding():
    fake_response = SimpleNamespace(
        embeddings=[
            SimpleNamespace(values=[0.1] * 768)
        ]
    )

    fake_client = MagicMock()
    fake_client.aio.models.embed_content = AsyncMock(
        return_value=fake_response
    )
    fake_client.aio.aclose = AsyncMock()

    with patch(
        "backend.app.embeddings.genai.Client",
        return_value=fake_client,
    ):
        result = await embed_text(
            "Refunds require human approval."
        )

    assert len(result) == 768
    fake_client.aio.models.embed_content.assert_awaited_once()
    fake_client.aio.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_failure_cleanup():
    fake_client = MagicMock()
    fake_client.aio.models.embed_content = AsyncMock(
        side_effect=RuntimeError("Simulated API failure")
    )
    fake_client.aio.aclose = AsyncMock()

    with patch(
        "backend.app.embeddings.genai.Client",
        return_value=fake_client,
    ):
        with pytest.raises(RuntimeError, match="Simulated"):
            await embed_text("Test document")

    fake_client.aio.aclose.assert_awaited_once()
