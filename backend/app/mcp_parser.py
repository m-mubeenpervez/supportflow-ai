
"""
Parse structured results returned by MCP business tools.
"""

import json
from typing import Any


class MCPResponseError(ValueError):
    """Raised when an MCP response is invalid."""


def parse_mcp_result(result: Any) -> dict | list:
    """
    Convert an MCP tool result into a Python dict or list.

    Raises MCPResponseError if the result is missing,
    malformed, or contains an unsupported data type.
    """

    if result.isError:
        raise MCPResponseError("MCP tool returned an error")

    structured = getattr(result, "structuredContent", None)

    if structured is not None:
        if not isinstance(structured, (dict, list)):
            raise MCPResponseError(
                "Unsupported structured MCP response"
            )
        return structured

    for block in result.content:
        if block.type != "text":
            continue

        try:
            data = json.loads(block.text)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, (dict, list)):
            return data

    raise MCPResponseError(
        "No valid structured data found in MCP response"
    )
