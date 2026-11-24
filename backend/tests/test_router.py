
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import graph as graph_module


@pytest.mark.asyncio
async def test_primary_router_success(monkeypatch):
    """Primary Gemini model returns a valid intent."""

    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(content="refund")
        )
    )

    monkeypatch.setattr(
        graph_module,
        "ChatGoogleGenerativeAI",
        lambda **kwargs: mock_llm,
    )

    monkeypatch.setattr(
        graph_module.settings,
        "gemini_api_key",
        "fake-test-key",
    )

    result = await graph_module.classify({
        "message": "My item arrived damaged",
        "customer_id": 1,
    })

    assert result["intent"] == "refund"
    assert mock_llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_primary_failure_uses_fallback(monkeypatch):
    """Fallback model is used after primary failure."""

    calls = []

    def fake_model(**kwargs):
        calls.append(kwargs["model"])

        if len(calls) == 1:
            return SimpleNamespace(
                ainvoke=AsyncMock(
                    side_effect=RuntimeError("Primary unavailable")
                )
            )

        return SimpleNamespace(
            ainvoke=AsyncMock(
                return_value=SimpleNamespace(content="delivery")
            )
        )

    monkeypatch.setattr(
        graph_module,
        "ChatGoogleGenerativeAI",
        fake_model,
    )

    monkeypatch.setattr(
        graph_module.settings,
        "gemini_api_key",
        "fake-test-key",
    )

    result = await graph_module.classify({
        "message": "Where is my shipment?",
        "customer_id": 1,
    })

    assert result["intent"] == "delivery"
    assert calls == [
        graph_module.settings.gemini_routing_model,
        graph_module.settings.gemini_routing_fallback_model,
    ]


@pytest.mark.asyncio
async def test_invalid_intent_uses_local_fallback(monkeypatch):
    """Invalid Gemini output uses the existing local fallback."""

    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(content="unknown")
        )
    )

    monkeypatch.setattr(
        graph_module,
        "ChatGoogleGenerativeAI",
        lambda **kwargs: mock_llm,
    )

    monkeypatch.setattr(
        graph_module.settings,
        "gemini_api_key",
        "fake-test-key",
    )

    result = await graph_module.classify({
        "message": "Please cancel my order ORD1023",
        "customer_id": 1,
    })

    assert result["intent"] == "cancel"
    assert result["order_id"] == "ORD1023"


@pytest.mark.asyncio
async def test_all_models_fail_uses_local_fallback(monkeypatch):
    """Both Gemini models fail; local routing remains available."""

    calls = []

    def fake_model(**kwargs):
        calls.append(kwargs["model"])

        return SimpleNamespace(
            ainvoke=AsyncMock(
                side_effect=RuntimeError("API unavailable")
            )
        )

    monkeypatch.setattr(
        graph_module,
        "ChatGoogleGenerativeAI",
        fake_model,
    )

    monkeypatch.setattr(
        graph_module.settings,
        "gemini_api_key",
        "fake-test-key",
    )

    result = await graph_module.classify({
        "message": "I need a refund",
        "customer_id": 1,
    })

    assert result["intent"] == "refund"
    assert len(calls) == 2



@pytest.mark.asyncio
async def test_valid_general_intent_is_not_overridden(monkeypatch):
    """A valid Gemini general intent must not be overridden by keywords."""

    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(content="general")
        )
    )

    monkeypatch.setattr(
        graph_module,
        "ChatGoogleGenerativeAI",
        lambda **kwargs: mock_llm,
    )

    monkeypatch.setattr(
        graph_module.settings,
        "gemini_api_key",
        "fake-test-key",
    )

    result = await graph_module.classify({
        "message": "I don't want to cancel my order. I just have a question.",
        "customer_id": 1,
    })

    assert result["intent"] == "general"
    assert mock_llm.ainvoke.await_count == 1



@pytest.mark.asyncio
async def test_rate_limit_skips_model_fallback(monkeypatch):
    """A quota error must not trigger another Gemini request."""

    from google.api_core.exceptions import ResourceExhausted

    calls = []

    def fake_model(**kwargs):
        calls.append(kwargs["model"])

        return SimpleNamespace(
            ainvoke=AsyncMock(
                side_effect=ResourceExhausted(
                    "429 RESOURCE_EXHAUSTED"
                )
            )
        )

    monkeypatch.setattr(
        graph_module,
        "ChatGoogleGenerativeAI",
        fake_model,
    )

    monkeypatch.setattr(
        graph_module.settings,
        "gemini_api_key",
        "fake-test-key",
    )

    result = await graph_module.classify({
        "message": "Please cancel my order",
        "customer_id": 1,
    })

    assert result["intent"] == "cancel"
    assert len(calls) == 1


def test_order_id_can_continue_from_customer_history_only():
    assert graph_module.extract_order_id(
        "Can I still request the refund?",
        [{"role": "user", "content": "My order is ORD1023"}],
    ) == "ORD1023"
    assert graph_module.extract_order_id(
        "Can I still request the refund?",
        [{"role": "assistant", "content": "Use ORD9999"}],
    ) is None
