
"""
SupportFlow AI internal MCP business tools.

Security boundary:
- This stdio MCP server is intended only for trusted backend processes.
- Do not expose it directly to customers or untrusted MCP clients.
- Tool customer_id arguments are NOT authentication.
- Customer identity must be verified by the FastAPI JWT layer.
- A trusted MCP client must pass only the authenticated customer ID.
- Read-only tools cannot execute refunds or cancellations.

Production deployment requires stronger MCP-level authorization
if this server becomes independently accessible.
"""

from mcp.server.fastmcp import FastMCP
from .tools import get_order_details, get_customer_details, get_ticket
from .semantic_search import semantic_search
from .policies import search_policies
from .config import settings
import logging


mcp=FastMCP('SupportFlow Business Tools')
@mcp.tool()
async def customer_details(customer_id:int)->dict:
    """Retrieve a customer's own profile. Caller must authenticate customer_id."""
    return await get_customer_details(customer_id)
@mcp.tool()
async def order_details(customer_id:int,order_id:str)->dict:
    """Read order details scoped to authenticated customer."""
    return await get_order_details(customer_id,order_id)
@mcp.tool()
async def ticket_details(ticket_id:int,customer_id:int)->dict:
    """Read a ticket scoped to authenticated customer."""
    return await get_ticket(ticket_id,customer_id)
@mcp.tool()
async def knowledge_search(query: str) -> list[dict]:
    """Retrieve support policies with configured semantic search."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if not settings.gemini_api_key:
        return search_policies(query)

    try:
        results = await semantic_search(query, top_k=3)
        if results:
            return results
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Semantic policy retrieval unavailable: %s",
            type(exc).__name__,
        )

    # Policy-only fallback. Does not verify orders or perform writes.
    return search_policies(query)
if __name__=='__main__': mcp.run(transport='stdio')
