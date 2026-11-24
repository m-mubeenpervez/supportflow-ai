
import pytest

from app.mcp_security import (
    MCPAuthorizationError,
    require_customer_access,
)


def test_matching_customer_ids_allowed():
    """Authenticated customer can access their own resources."""

    result = require_customer_access(
        authenticated_customer_id=10,
        requested_customer_id=10,
    )

    assert result == 10


def test_different_customer_ids_rejected():
    """Customer cannot access another customer's resources."""

    with pytest.raises(MCPAuthorizationError):
        require_customer_access(
            authenticated_customer_id=10,
            requested_customer_id=20,
        )


def test_missing_authenticated_identity_rejected():
    """Missing authentication must deny access."""

    with pytest.raises(MCPAuthorizationError):
        require_customer_access(
            authenticated_customer_id=None,
            requested_customer_id=10,
        )


def test_invalid_authenticated_identity_rejected():
    """Invalid authenticated customer IDs must be rejected."""

    for invalid_id in [0, -1, True, "10"]:
        with pytest.raises(MCPAuthorizationError):
            require_customer_access(
                authenticated_customer_id=invalid_id,
                requested_customer_id=10,
            )


def test_invalid_requested_customer_id_rejected():
    """Invalid requested customer IDs must be rejected."""

    for invalid_id in [0, -1, True, "10", None]:
        with pytest.raises(MCPAuthorizationError):
            require_customer_access(
                authenticated_customer_id=10,
                requested_customer_id=invalid_id,
            )
