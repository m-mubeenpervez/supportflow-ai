"""Isolated administrator JWT unit tests."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.admin_auth import (
    ADMIN_TOKEN_TYPE,
    create_admin_access_token,
    decode_admin_access_token,
)
from app.auth import create_access_token, decode_access_token
from app.config import settings


@pytest.fixture(autouse=True)
def isolated_jwt_secret(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        "isolated-admin-jwt-unit-test-key-not-for-production",
    )


def test_valid_admin_jwt():
    token = create_admin_access_token(7, 2)
    assert decode_admin_access_token(token) == (7, 2)


def test_customer_jwt_rejected_as_admin():
    token = create_access_token(7, 2)
    assert decode_admin_access_token(token) is None


def test_admin_jwt_rejected_as_customer():
    token = create_admin_access_token(7, 2)
    assert decode_access_token(token) is None


def test_tampered_admin_jwt_rejected():
    token = create_admin_access_token(7, 2)
    parts = token.split(".")
    parts[2] = "invalid-signature"
    assert decode_admin_access_token(
        ".".join(parts)
    ) is None


def test_expired_admin_jwt_rejected():
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "7",
            "iat": now - timedelta(minutes=40),
            "exp": now - timedelta(minutes=20),
            "type": ADMIN_TOKEN_TYPE,
            "sv": 2,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_admin_access_token(token) is None


@pytest.mark.parametrize(
    "admin_id,version",
    [(0, 0), (-1, 0), (True, 0), (7, -1), (7, True)],
)
def test_invalid_admin_token_inputs(admin_id, version):
    with pytest.raises(ValueError):
        create_admin_access_token(admin_id, version)


@pytest.mark.parametrize(
    "version",
    [-1, "2", True, None],
)
def test_invalid_session_version_rejected(version):
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "7",
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "type": ADMIN_TOKEN_TYPE,
            "sv": version,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_admin_access_token(token) is None


def test_missing_admin_token_claim_rejected():
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "7",
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "type": ADMIN_TOKEN_TYPE,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_admin_access_token(token) is None


def test_invalid_admin_token_string_rejected():
    assert decode_admin_access_token("") is None
    assert decode_admin_access_token("not-a-jwt") is None
