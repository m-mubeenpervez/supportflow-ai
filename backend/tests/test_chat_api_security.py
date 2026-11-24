
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_chat_rejects_missing_jwt():
    """Chat endpoint must reject unauthenticated requests."""

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/chat",
            json={
                "message": "Where is my order ORD1023?"
            },
        )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid or missing authentication token"
    }

    assert response.headers["www-authenticate"] == "Bearer"



@pytest.mark.asyncio
async def test_chat_rejects_invalid_jwt():
    """Chat endpoint must reject an invalid JWT."""

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/chat",
            headers={
                "Authorization": "Bearer invalid.jwt.token"
            },
            json={
                "message": "Where is my order ORD1023?"
            },
        )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid or missing authentication token"
    }

    assert response.headers["www-authenticate"] == "Bearer"
