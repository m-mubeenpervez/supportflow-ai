
import pytest

from app.mcp_client import call_business_tool
from app.mcp_security import MCPAuthorizationError


@pytest.mark.asyncio
async def test_disallowed_tool_rejected():
    """Unknown MCP tools must be blocked."""

    with pytest.raises(ValueError, match="not allowed"):
        await call_business_tool(
            tool_name="delete_customer",
            arguments={},
            authenticated_customer_id=10,
        )


@pytest.mark.asyncio
async def test_missing_authenticated_identity_rejected():
    """MCP tools require authenticated identity."""

    with pytest.raises(PermissionError):
        await call_business_tool(
            tool_name="order_details",
            arguments={"order_id": "ORD1023"},
            authenticated_customer_id=None,
        )


@pytest.mark.asyncio
async def test_cross_customer_access_rejected():
    """Caller cannot request another customer's data."""

    with pytest.raises(MCPAuthorizationError):
        await call_business_tool(
            tool_name="order_details",
            arguments={
                "customer_id": 20,
                "order_id": "ORD1023",
            },
            authenticated_customer_id=10,
        )


@pytest.mark.asyncio
async def test_invalid_customer_identity_rejected():
    """Boolean and negative IDs are invalid identities."""

    for invalid_id in [True, 0, -1, "10"]:
        with pytest.raises(PermissionError):
            await call_business_tool(
                tool_name="customer_details",
                arguments={},
                authenticated_customer_id=invalid_id,
            )


@pytest.mark.asyncio
async def test_knowledge_search_requires_authentication():
    """Even policy search requires a trusted caller."""

    with pytest.raises(PermissionError):
        await call_business_tool(
            tool_name="knowledge_search",
            arguments={"query": "refund policy"},
            authenticated_customer_id=None,
        )
