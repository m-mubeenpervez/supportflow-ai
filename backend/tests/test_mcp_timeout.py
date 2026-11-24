import pytest

from app.mcp_client import call_business_tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name, arguments, expected_timeout",
    [
        (
            "knowledge_search",
            {"query": "refund policy"},
            45.0,
        ),
        (
            "order_details",
            {"order_id": "ORD1023"},
            10.0,
        ),
    ],
)
async def test_mcp_client_timeout(
    monkeypatch,
    tool_name,
    arguments,
    expected_timeout,
):
    """MCP tools must raise controlled timeout errors."""

    async def fake_wait_for(awaitable, timeout):
        try:
            assert timeout == expected_timeout
        finally:
            # Prevent an unawaited coroutine warning.
            awaitable.close()

        raise TimeoutError("Simulated timeout")

    monkeypatch.setattr(
        "app.mcp_client.asyncio.wait_for",
        fake_wait_for,
    )

    with pytest.raises(
        TimeoutError,
        match=f"MCP tool timed out: {tool_name}",
    ):
        await call_business_tool(
            tool_name=tool_name,
            arguments=arguments,
            authenticated_customer_id=1,
        )
