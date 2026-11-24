
import json
from types import SimpleNamespace

import pytest

from app.graph import retrieve


@pytest.mark.asyncio
async def test_retrieve_uses_mcp_tools(monkeypatch):
    calls = []

    async def fake_call_business_tool(
        tool_name,
        arguments,
        authenticated_customer_id,
    ):
        calls.append({
            "tool": tool_name,
            "arguments": arguments,
            "customer_id": authenticated_customer_id,
        })

        if tool_name == "order_details":
            data = {
                "id": "ORD1023",
                "status": "delivered",
                "item": "Wireless Headphones",
                "total": 4999,
            }

        elif tool_name == "knowledge_search":
            data = {
                "result": [
                    {
                        "source": "delivery",
                        "text": "Check shipment status.",
                    }
                ]
            }

        else:
            raise AssertionError("Unexpected MCP tool")

        return SimpleNamespace(
            isError=False,
            structuredContent=None,
            content=[
                SimpleNamespace(
                    type="text",
                    text=json.dumps(data),
                )
            ],
        )

    monkeypatch.setattr(
        "app.graph.call_business_tool",
        fake_call_business_tool,
    )

    state = {
        "message": "Where is my order ORD1023?",
        "customer_id": 1,
        "intent": "delivery",
        "order_id": "ORD1023",
    }

    result = await retrieve(state)

    assert result["order"]["id"] == "ORD1023"
    assert result["order"]["status"] == "delivered"

    assert isinstance(result["sources"], list)
    assert result["sources"][0]["source"] == "delivery"

    assert calls == [
        {
            "tool": "order_details",
            "arguments": {"order_id": "ORD1023"},
            "customer_id": 1,
        },
        {
            "tool": "knowledge_search",
            "arguments": {
                "query": "delivery Where is my order ORD1023?"
            },
            "customer_id": 1,
        },
    ]



@pytest.mark.asyncio
async def test_retrieve_handles_mcp_connection_failure(monkeypatch):
    """MCP failure must not expose or invent order details."""

    async def failing_mcp_call(
        tool_name,
        arguments,
        authenticated_customer_id,
    ):
        raise ConnectionError("Simulated MCP server failure")

    monkeypatch.setattr(
        "app.graph.call_business_tool",
        failing_mcp_call,
    )

    state = {
        "message": "Where is my order ORD1023?",
        "customer_id": 1,
        "intent": "delivery",
        "order_id": "ORD1023",
    }

    result = await retrieve(state)

    assert result["order"] == {
        "error": "Order verification unavailable"
    }

    assert result["sources"] == []

    assert "status" not in result["order"]
    assert "total" not in result["order"]



from app.graph import draft


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intent",
    ["delivery", "refund", "cancel"],
)
async def test_draft_blocks_unverified_order_after_mcp_failure(
    intent,
    monkeypatch,
):
    """Unverified orders must not trigger AI or approval."""

    def unexpected_llm(*args, **kwargs):
        raise AssertionError(
            "Gemini must not be called for unverified orders"
        )

    monkeypatch.setattr(
        "app.graph.ChatGoogleGenerativeAI",
        unexpected_llm,
    )

    state = {
        "message": "Please help with order ORD1023",
        "customer_id": 1,
        "intent": intent,
        "order_id": "ORD1023",
        "order": {
            "error": "Order verification unavailable"
        },
        "sources": [],
    }

    result = await draft(state)

    assert result["needs_approval"] is False


    assert result["draft"] == (
        "Our order verification service is temporarily "
        "unavailable. Please try again shortly. "
        "No changes have been made to your order."
    )




from app.graph import graph


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, expected_intent",
    [
        ("Where is my order ORD1023?", "delivery"),
        ("Refund my order ORD1023", "refund"),
        ("Cancel my order ORD1023", "cancel"),
    ],
)
async def test_complete_graph_handles_mcp_failure(
    message,
    expected_intent,
    monkeypatch,
):
    """Full LangGraph must fail safely if MCP is unavailable."""

    async def failing_mcp_call(
        tool_name,
        arguments,
        authenticated_customer_id,
    ):
        raise ConnectionError("Simulated MCP failure")

    def unexpected_llm(*args, **kwargs):
        raise AssertionError(
            "Gemini should not be called in this test"
        )

    monkeypatch.setattr(
        "app.graph.call_business_tool",
        failing_mcp_call,
    )

    monkeypatch.setattr(
        "app.graph.ChatGoogleGenerativeAI",
        unexpected_llm,
    )

    monkeypatch.setattr(
        "app.graph.settings.gemini_api_key",
        "",
    )

    result = await graph.ainvoke({
        "message": message,
        "customer_id": 1,
    })

    assert result["intent"] == expected_intent
    assert result["order_id"] == "ORD1023"

    assert result["order"] == {
        "error": "Order verification unavailable"
    }

    assert result["sources"] == []

    assert result["needs_approval"] is False


    assert result["draft"] == (
        "Our order verification service is temporarily "
        "unavailable. Please try again shortly. "
        "No changes have been made to your order."
    )




@pytest.mark.asyncio
async def test_complete_graph_handles_mcp_timeout(monkeypatch):
    """Full LangGraph must fail safely on MCP timeout."""

    async def timeout_mcp_call(
        tool_name,
        arguments,
        authenticated_customer_id,
    ):
        raise TimeoutError(
            f"MCP tool timed out: {tool_name}"
        )

    def unexpected_llm(*args, **kwargs):
        raise AssertionError(
            "Gemini must not be called during this test"
        )

    monkeypatch.setattr(
        "app.graph.call_business_tool",
        timeout_mcp_call,
    )

    monkeypatch.setattr(
        "app.graph.ChatGoogleGenerativeAI",
        unexpected_llm,
    )

    monkeypatch.setattr(
        "app.graph.settings.gemini_api_key",
        "",
    )

    result = await graph.ainvoke({
        "message": "Refund my order ORD1023",
        "customer_id": 1,
    })

    assert result["intent"] == "refund"
    assert result["order_id"] == "ORD1023"

    assert result["order"] == {
        "error": "Order verification unavailable"
    }

    assert result["sources"] == []
    assert result["needs_approval"] is False


    assert result["draft"] == (
        "Our order verification service is temporarily "
        "unavailable. Please try again shortly. "
        "No changes have been made to your order."
    )



@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intent",
    ["delivery", "refund", "cancel"],
)
async def test_draft_handles_invalid_order_safely(
    intent,
    monkeypatch,
):
    """Invalid orders must not trigger Gemini or approval."""

    def unexpected_llm(*args, **kwargs):
        raise AssertionError(
            "Gemini must not be called for invalid orders"
        )

    monkeypatch.setattr(
        "app.graph.ChatGoogleGenerativeAI",
        unexpected_llm,
    )

    state = {
        "message": "Please help with order ORD9999",
        "customer_id": 1,
        "intent": intent,
        "order_id": "ORD9999",
        "order": {
            "error": "Order not found or access denied"
        },
        "sources": [],
    }

    result = await draft(state)

    assert result["needs_approval"] is False

    assert result["draft"] == (
        "I could not verify that order for your account. "
        "Please check the order ID."
    )
