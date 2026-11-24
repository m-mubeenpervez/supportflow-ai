import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app import main as main_module
from app.main import app, admin


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [
            {
                "id": 123456,
                "name": "Synthetic Customer",
                "email": "synthetic@example.invalid",
                "email_verified_at": datetime.now(timezone.utc),
                "deactivated_at": None,
                "ticket_count": 2,
            },
            {
                "id": 123455,
                "name": "Disabled Customer",
                "email": "disabled@example.invalid",
                "email_verified_at": None,
                "deactivated_at": datetime.now(timezone.utc),
                "ticket_count": 0,
            },
        ]


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def scalar(self, statement):
        return 2

    async def execute(self, statement):
        return FakeResult()


async def get_customers(params=None, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(
            "/admin/customers",
            params=params,
            headers=headers or {},
        )


def test_missing_admin_token_rejected():
    response = asyncio.run(get_customers())
    assert response.status_code in (401, 403)


@pytest.fixture
def authorized_environment(monkeypatch):
    # Override admin identity only in the authorized data tests.
    # Missing-token test above exercises the real admin guard.
    app.dependency_overrides[admin] = lambda: True
    monkeypatch.setattr(
        main_module,
        "Session",
        FakeSession,
    )

    yield

    app.dependency_overrides.pop(admin, None)


def test_customer_list_is_safe(authorized_environment):
    response = asyncio.run(get_customers())

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert data["limit"] == 25
    assert data["offset"] == 0

    first, second = data["customers"]

    assert first["id"] == 123456
    assert first["email_verified"] is True
    assert first["status"] == "active"
    assert first["ticket_count"] == 2

    assert second["email_verified"] is False
    assert second["status"] == "deactivated"

    for customer in data["customers"]:
        assert "password_hash" not in customer
        assert "session_version" not in customer
        assert "jwt" not in customer


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 51},
        {"offset": -1},
        {"offset": 1000001},
    ],
)
def test_invalid_pagination_rejected(
    authorized_environment,
    params,
):
    response = asyncio.run(get_customers(params=params))
    assert response.status_code == 422

def test_invalid_admin_token_rejected(monkeypatch):
    """A wrong admin token must not grant access."""
    monkeypatch.setattr(
        main_module.settings,
        "admin_token",
        "isolated-test-admin-token-274215",
    )

    response = asyncio.run(
        get_customers(
            headers={"X-Admin-Token": "invalid-test-token"}
        )
    )

    # JWT mode returns 401 for missing/invalid Bearer credentials.
    # Legacy mode returns 403 for an incorrect shared token.
    jwt_mode = main_module.admin is main_module.get_current_admin
    assert response.status_code == (401 if jwt_mode else 403)


def test_customer_bearer_cannot_access_admin_customers(monkeypatch):
    """A valid customer JWT alone must not grant admin access."""
    from app.auth import create_access_token

    monkeypatch.setattr(
        main_module.settings,
        "admin_token",
        "isolated-test-admin-token-274215",
    )

    customer_jwt = create_access_token(123456)

    response = asyncio.run(
        get_customers(
            headers={
                "Authorization": f"Bearer {customer_jwt}"
            }
        )
    )

    jwt_mode = main_module.admin is main_module.get_current_admin
    assert response.status_code == (401 if jwt_mode else 403)


def test_valid_admin_header_grants_customer_list_access(monkeypatch):
    """The real admin dependency must accept a matching test token."""
    test_token = "isolated-test-admin-token-274215"

    monkeypatch.setattr(
        main_module.settings,
        "admin_token",
        test_token,
    )
    monkeypatch.setattr(
        main_module,
        "Session",
        FakeSession,
    )

    response = asyncio.run(
        get_customers(
            headers={"X-Admin-Token": test_token}
        )
    )

    jwt_mode = main_module.admin is main_module.get_current_admin
    if jwt_mode:
        # Critical regression: valid legacy header must NEVER bypass JWT auth.
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"
    else:
        assert response.status_code == 200
        assert response.json()["total"] == 2
