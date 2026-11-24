
"""
Authorization helpers for internal MCP tools.

Important:
The authenticated customer ID must come from a trusted
authentication boundary, never from an untrusted tool argument.
"""


class MCPAuthorizationError(PermissionError):
    """Raised when MCP customer access is not authorized."""


def require_customer_access(
    authenticated_customer_id: int | None,
    requested_customer_id: int,
) -> int:
    """
    Verify that a customer can access their own resources.

    authenticated_customer_id:
        Customer identity established by a trusted auth layer.

    requested_customer_id:
        Customer identity requested by an MCP tool.
    """

    if (
        type(authenticated_customer_id) is not int
        or authenticated_customer_id <= 0
    ):
        raise MCPAuthorizationError(
            "Authenticated customer identity is required"
        )

    if (
        type(requested_customer_id) is not int
        or requested_customer_id != authenticated_customer_id
    ):
        raise MCPAuthorizationError(
            "Customer resource access denied"
        )

    return authenticated_customer_id
