"""Isolated HTTP tests for administrator login."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app import admin_routes
from app.admin_auth import decode_admin_access_token
from app.config import settings


app = FastAPI()
app.include_router(admin_routes.router)

TEST_PASSWORD = "TestAdminPassword123!"


class FakeSession:
    def __init__(self, record):
        self.record = record

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalar(self, statement):
        return self.record


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    from app.admin_login_throttle import AdminLoginThrottle

    monkeypatch.setattr(
        admin_routes,
        "admin_login_throttle",
        AdminLoginThrottle(),
    )
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        "isolated-admin-login-test-key-with-adequate-length-2026",
    )
    monkeypatch.setattr(
        admin_routes,
        "verify_password",
        lambda password, hashed: (
            password == TEST_PASSWORD
            and hashed == "synthetic-test-hash"
        ),
    )


def make_account(**changes):
    values = {
        "id": 7,
        "email": "admin@example.com",
        "password_hash": "synthetic-test-hash",
        "role": "admin",
        "is_active": True,
        "session_version": 2,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def configure(monkeypatch, record):
    monkeypatch.setattr(
        admin_routes,
        "Session",
        lambda: FakeSession(record),
    )


def request(password=TEST_PASSWORD):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(
                "/admin/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": password,
                },
            )
    return asyncio.run(send())


def test_valid_admin_login(monkeypatch):
    configure(monkeypatch, make_account())
    response = request()
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert decode_admin_access_token(token) == (7, 2)


def test_unknown_admin_rejected(monkeypatch):
    configure(monkeypatch, None)
    response = request()
    assert response.status_code == 401


def test_invalid_password_rejected(monkeypatch):
    configure(monkeypatch, make_account())
    response = request("WrongPassword")
    assert response.status_code == 401


def test_inactive_admin_rejected(monkeypatch):
    configure(monkeypatch, make_account(is_active=False))
    response = request()
    assert response.status_code == 401


def test_invalid_admin_role_rejected(monkeypatch):
    configure(monkeypatch, make_account(role="customer"))
    response = request()
    assert response.status_code == 401


def test_invalid_session_version_rejected(monkeypatch):
    configure(
        monkeypatch,
        make_account(session_version=-1),
    )
    response = request()
    assert response.status_code == 401


def test_super_admin_login(monkeypatch):
    configure(
        monkeypatch,
        make_account(role="super_admin"),
    )
    response = request()
    assert response.status_code == 200
    assert decode_admin_access_token(
        response.json()["access_token"]
    ) == (7, 2)

def test_unknown_admin_still_checks_password(monkeypatch):
    """Unknown accounts must perform dummy password verification."""
    configure(monkeypatch, None)

    monkeypatch.setattr(
        admin_routes,
        "_dummy_admin_password_hash",
        lambda: "synthetic-dummy-hash",
    )

    calls = []

    def check_password(password, hashed):
        calls.append((password, hashed))
        return False

    monkeypatch.setattr(
        admin_routes,
        "verify_password",
        check_password,
    )

    response = request()

    assert response.status_code == 401
    assert calls == [
        (TEST_PASSWORD, "synthetic-dummy-hash")
    ]


def test_oversized_admin_password_rejected(monkeypatch):
    """Avoid processing unbounded password inputs."""
    configure(monkeypatch, make_account())

    response = request("A" * 129)

    assert response.status_code == 422

def test_admin_me_returns_safe_profile():
    from app.admin_dependencies import get_current_admin

    record = make_account()
    app.dependency_overrides[get_current_admin] = lambda: record

    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/admin/auth/me")

    try:
        response = asyncio.run(send())
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 7
        assert data["role"] == "admin"
        assert "password_hash" not in data
        assert "session_version" not in data
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_admin_me_requires_authentication():
    from app.admin_dependencies import get_current_admin

    app.dependency_overrides.pop(get_current_admin, None)

    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/admin/auth/me")

    response = asyncio.run(send())
    assert response.status_code == 401


def test_admin_logout_revokes_sessions(monkeypatch):
    from app.admin_dependencies import get_current_admin

    record = make_account()
    app.dependency_overrides[get_current_admin] = lambda: record

    operations = []

    class LogoutResult:
        def scalar_one_or_none(self):
            return 7

    class LogoutSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            sql = str(statement)
            assert "UPDATE admin_users" in sql
            assert "session_version" in sql
            operations.append("execute")
            return LogoutResult()

        async def commit(self):
            operations.append("commit")

        async def rollback(self):
            operations.append("rollback")

    monkeypatch.setattr(
        admin_routes,
        "Session",
        lambda: LogoutSession(),
    )

    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post("/admin/auth/logout")

    try:
        response = asyncio.run(send())
        assert response.status_code == 200
        assert operations == ["execute", "commit"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_admin_logout_rejects_stale_session(monkeypatch):
    from app.admin_dependencies import get_current_admin

    record = make_account()
    app.dependency_overrides[get_current_admin] = lambda: record

    operations = []

    class LogoutResult:
        def scalar_one_or_none(self):
            return None

    class LogoutSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            operations.append("execute")
            return LogoutResult()

        async def commit(self):
            operations.append("commit")

        async def rollback(self):
            operations.append("rollback")

    monkeypatch.setattr(
        admin_routes,
        "Session",
        lambda: LogoutSession(),
    )

    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post("/admin/auth/logout")

    try:
        response = asyncio.run(send())
        assert response.status_code == 401
        assert operations == ["execute", "rollback"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)

def request_from_client(ip, password):
    """Send a simulated direct-client HTTP login request."""

    async def send():
        transport = httpx.ASGITransport(
            app=app,
            client=(ip, 12345),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(
                "/admin/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": password,
                },
            )

    return asyncio.run(send())


def test_admin_login_returns_429_after_five_failures(monkeypatch):
    configure(monkeypatch, make_account())

    for _ in range(5):
        response = request_from_client(
            "198.51.100.10",
            "incorrect-password",
        )
        assert response.status_code == 401

    response = request_from_client(
        "198.51.100.10",
        TEST_PASSWORD,
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "300"


def test_admin_login_throttle_isolates_client_addresses(monkeypatch):
    configure(monkeypatch, make_account())

    for _ in range(5):
        response = request_from_client(
            "198.51.100.11",
            "incorrect-password",
        )
        assert response.status_code == 401

    blocked = request_from_client(
        "198.51.100.11",
        TEST_PASSWORD,
    )

    allowed = request_from_client(
        "198.51.100.12",
        TEST_PASSWORD,
    )

    assert blocked.status_code == 429
    assert allowed.status_code == 200


def test_successful_admin_login_clears_failures(monkeypatch):
    configure(monkeypatch, make_account())
    ip = "198.51.100.13"

    for _ in range(2):
        response = request_from_client(
            ip,
            "incorrect-password",
        )
        assert response.status_code == 401

    successful = request_from_client(
        ip,
        TEST_PASSWORD,
    )
    assert successful.status_code == 200

    # After successful login the client gets a fresh allowance.
    for _ in range(5):
        response = request_from_client(
            ip,
            "incorrect-password",
        )
        assert response.status_code == 401

    blocked = request_from_client(
        ip,
        TEST_PASSWORD,
    )
    assert blocked.status_code == 429

def test_inflight_reservations_block_admin_login(monkeypatch):
    """Active requests must count against the admission limit."""
    configure(monkeypatch, make_account())

    throttle = admin_routes.admin_login_throttle
    ip = "198.51.100.70"

    for _ in range(5):
        assert throttle.begin_attempt(ip)

    try:
        response = request_from_client(ip, TEST_PASSWORD)

        assert response.status_code == 429
        assert throttle.inflight[ip] == 5
    finally:
        for _ in range(5):
            throttle.finish_attempt(ip, success=True)

    assert ip not in throttle.inflight


def test_database_failure_releases_login_reservation(monkeypatch):
    """Unexpected database errors must not leak active slots."""
    ip = "198.51.100.71"

    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("Synthetic database failure")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        admin_routes,
        "Session",
        lambda: BrokenSession(),
    )

    async def send():
        transport = httpx.ASGITransport(
            app=app,
            client=(ip, 12345),
            raise_app_exceptions=False,
        )

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(
                "/admin/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": TEST_PASSWORD,
                },
            )

    response = asyncio.run(send())

    throttle = admin_routes.admin_login_throttle

    assert response.status_code == 500
    assert ip not in throttle.inflight
    assert len(throttle.failures[ip]) == 1
