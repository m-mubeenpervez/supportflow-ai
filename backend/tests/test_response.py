
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import ResourceExhausted

from app import graph as graph_module


def sample_state(intent="delivery", order=None):
    return {
        "message": "Where is my order ORD1023?",
        "customer_id": 1,
        "intent": intent,
        "order_id": "ORD1023",
        "order": order if order is not None else {
            "id": "ORD1023",
            "status": "shipped",
        },
        "sources": [
            {
                "source": "delivery",
                "text": "Check shipment status.",
            }
        ],
    }


@pytest.mark.asyncio
async def test_primary_response_success(monkeypatch):
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(
                content="Your order has been shipped."
            )
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

    result = await graph_module.draft(sample_state())

    assert result["draft"] == "Your order has been shipped."
    assert result["needs_approval"] is False
    assert mock_llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_primary_response_failure_uses_fallback(monkeypatch):
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
                return_value=SimpleNamespace(
                    content="Your shipment is on its way."
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

    result = await graph_module.draft(sample_state())

    assert result["draft"] == "Your shipment is on its way."
    assert calls == [
        graph_module.settings.gemini_response_model,
        graph_module.settings.gemini_response_fallback_model,
    ]


@pytest.mark.asyncio
async def test_rate_limit_skips_response_fallback(monkeypatch):
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

    result = await graph_module.draft(sample_state())

    assert len(calls) == 1
    assert "shipped" in result["draft"].lower()
    assert result["needs_approval"] is False


@pytest.mark.asyncio
async def test_unverified_order_skips_gemini(monkeypatch):
    calls = []

    def fake_model(**kwargs):
        calls.append(kwargs)
        raise AssertionError("Gemini must not be called")

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

    result = await graph_module.draft(
        sample_state(
            order={"error": "Order does not belong to customer"}
        )
    )

    assert "could not verify" in result["draft"].lower()
    assert result["needs_approval"] is False
    assert calls == []


@pytest.mark.asyncio
async def test_refund_requires_human_approval(monkeypatch):
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(
                content="Our team will review your refund request."
            )
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

    result = await graph_module.draft(
        sample_state(intent="refund")
    )

    assert result["needs_approval"] is True




@pytest.mark.asyncio
async def test_missing_order_id_skips_gemini(monkeypatch):
    """Order-specific requests without an ID must ask for one."""

    calls = []

    def fake_model(**kwargs):
        calls.append(kwargs)
        raise AssertionError("Gemini must not be called")

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

    state = sample_state(intent="delivery")
    state["order_id"] = None
    state["order"] = {"notice": "No order ID supplied"}

    result = await graph_module.draft(state)

    assert "order ID" in result["draft"]
    assert result["needs_approval"] is False
    assert calls == []


@pytest.mark.parametrize("message", [
    "I received a damaged product 10 days ago. Am I eligible for a refund, and what do I need to provide?",
    "What if I don't have photos of the damaged product? Can I still request the refund?",
    "Are product photos mandatory when requesting a refund for a damaged item?",
])
def test_damaged_refund_questions_are_policy_questions(message):
    assert graph_module.is_policy_information_request(message) is True


def test_refund_policy_fallback_includes_evidence_and_approval_guidance():
    answer = graph_module.policy_fallback_response(
        "Are product photos mandatory when requesting a refund for a damaged item?",
        [],
    ).lower()
    assert "may be requested" in answer
    assert "order" in answer and "verify" in answer
    assert "human approval" in answer


def test_order_action_still_requires_order_id():
    assert graph_module.is_policy_information_request(
        "Please refund my order"
    ) is False


@pytest.mark.parametrize("message, policy_key", [
    ("Can I get a refund for a damaged item?", "refund"),
    ("What is the return and exchange process?", "returns"),
    ("Is it too late to cancel if the parcel is on its way?", "cancel"),
    ("What happens when a shipment is delayed?", "shipping"),
    ("How are duplicate payment charges handled?", "payments"),
    ("What are your privacy rules for customer data?", "privacy"),
    ("How do I raise a dispute about an order?", "disputes"),
])
def test_all_policy_fallbacks_are_grounded(message, policy_key):
    assert graph_module.is_policy_information_request(message)
    answer = graph_module.policy_fallback_response(message, []).lower()
    expected = {
        "refund": "refund",
        "returns": "photographic",
        "cancel": "cancelled",
        "shipping": "shipment",
        "payments": "authenticate",
        "privacy": "another customer's",
        "disputes": "disputes",
    }[policy_key]
    assert expected in answer


@pytest.mark.parametrize("message", [
    "Can I cancel my order if it has already been shipped? What are my options?",
    "According to your cancellation policy, are shipped orders eligible for cancellation?",
    "My package is already on its way. Is it too late to cancel it?",
])
def test_cancellation_paraphrases_are_informational(message):
    assert graph_module.is_policy_information_request(message)
    answer = graph_module.policy_fallback_response(message, []).lower()
    assert "cannot be cancelled" in answer
    assert "returns" in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("message, intent, expected", [
    (
        "My package is delayed and the tracking hasn't updated for three days. Can you tell me exactly when it will arrive?",
        "delivery",
        ("exact arrival time", "order ID", "escalate"),
    ),
    (
        "I think I was charged twice for the same order. Can you refund the extra payment immediately?",
        "general",
        ("duplicate", "authorized staff", "human approval", "order ID"),
    ),
])
async def test_missing_order_actions_include_grounded_policy_guidance(
    monkeypatch, message, intent, expected
):
    monkeypatch.setattr(graph_module.settings, "gemini_api_key", "")
    result = await graph_module.draft({
        "message": message,
        "customer_id": 1,
        "intent": intent,
        "order_id": None,
        "order": {"notice": "No order ID supplied"},
        "sources": [],
    })
    answer = result["draft"].lower()
    for phrase in expected:
        assert phrase.lower() in answer
    assert result["needs_approval"] is False


def test_sensitive_payment_question_directly_prohibits_secrets():
    answer = graph_module.policy_fallback_response(
        "Do I need to share my full card number, CVV, or OTP with you to investigate the duplicate charge?",
        [],
    )
    lowered = answer.lower()
    assert lowered.startswith("no.")
    for secret in ("full card", "cvv", "security code", "otp", "password"):
        assert secret in lowered
    assert "damaged" not in lowered


def test_missing_order_composition_has_one_disclaimer():
    answer = graph_module.policy_fallback_response(
        "I think I was charged twice for the same order. Can you refund the extra payment immediately?",
        [], include_disclaimer=False,
    )
    assert "No action has been taken" not in answer
    assert "No changes have been made" not in answer
