
"""
Internal MCP client for SupportFlow AI.

Launches the MCP server as a local subprocess.
Only trusted backend code should invoke this client.

Customer authorization must be enforced before
customer-specific tools are called.
"""

import sys
import asyncio
import os
from .config import settings
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .mcp_security import require_customer_access


BACKEND_ROOT = Path(__file__).resolve().parents[1]



async def call_business_tool(
    tool_name: str,
    arguments: dict,
    authenticated_customer_id: int,
):
    allowed_tools = {
        "customer_details",
        "order_details",
        "ticket_details",
        "knowledge_search",
    }

    if tool_name not in allowed_tools:
        raise ValueError("MCP tool is not allowed")

    if (
        type(authenticated_customer_id) is not int
        or authenticated_customer_id <= 0
    ):
        raise PermissionError(
            "Authenticated customer identity is required"
        )

    safe_arguments = dict(arguments)
    requested_id = safe_arguments.pop("customer_id", None)

    if tool_name != "knowledge_search":
        if requested_id is not None:
            require_customer_access(
                authenticated_customer_id,
                requested_id,
            )

        safe_arguments["customer_id"] = authenticated_customer_id

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        cwd=str(BACKEND_ROOT),
        env={
            **os.environ,
            "DATABASE_URL": settings.database_url,
        },
    )

    async def execute():
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    tool_name,
                    arguments=safe_arguments,
                )

                if result.isError:
                    raise RuntimeError(
                        f"MCP tool failed: {tool_name}"
                    )

                return result

    try:
        timeout_seconds = (
            45.0 if tool_name == "knowledge_search" else 10.0
        )

        return await asyncio.wait_for(
            execute(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        raise TimeoutError(
            f"MCP tool timed out: {tool_name}"
        ) from None
