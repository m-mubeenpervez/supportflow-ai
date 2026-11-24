
import asyncio

import pytest

from app.main import app, admin
from app import main as main_module

class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [
            {
                "id": 123456,
                "name": "Synthetic Customer",
                "email": "synthetic@example.invalid",
                "email_verified_at": None,
                "deactivated_at": None,
                "created_at": None,
                "ticket_count": 2,
            }
        ]


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def scalar(self, statement):
        return 1

    async def execute(self, statement):
        return FakeResult()



@pytest.fixture
def customer_date_environment(monkeypatch):
    app.dependency_overrides[admin] = lambda: True
    monkeypatch.setattr(main_module, "Session", FakeSession)
    yield
    app.dependency_overrides.pop(admin, None)


@pytest.mark.parametrize("params", [
    {"date_preset": "invalid"},
    {"date_preset": "custom", "date_from": "invalid"},
    {
        "date_preset": "custom",
        "date_from": "2026-11-20",
        "date_to": "2026-11-19",
    },
    {"date_preset": "today", "date_from": "2026-11-20"},
    {"time_from": "invalid"},
    {"time_to": "29:99"},
])
def test_invalid_customer_date_filters(
    customer_date_environment,
    params,
):
    import httpx

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/admin/customers",
                params=params,
            )

    response = asyncio.run(request())
    assert response.status_code == 422


@pytest.mark.parametrize("params", [
    {"date_preset": "today"},
    {"date_preset": "7days"},
    {"date_preset": "30days"},
    {
        "date_preset": "custom",
        "date_from": "2026-01-01",
        "date_to": "2026-12-31",
    },
    {"time_from": "22:00", "time_to": "02:00"},
])
def test_valid_customer_date_filters(
    customer_date_environment,
    params,
):
    import httpx

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/admin/customers",
                params=params,
            )

    response = asyncio.run(request())
    assert response.status_code == 200
