
from datetime import datetime, timedelta, timezone

import jwt

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.config import settings


def test_password_hashing():
    password = "SecurePassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_valid_jwt():
    token = create_access_token(customer_id=123)

    assert decode_access_token(token) == 123


def test_tampered_jwt():
    token = create_access_token(customer_id=123)

    parts = token.split(".")
    signature = parts[2]

    replacement = "A" if signature[0] != "A" else "B"
    parts[2] = replacement + signature[1:]

    tampered_token = ".".join(parts)

    assert decode_access_token(tampered_token) is None


def test_expired_jwt():
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "123",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "type": "access",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(token) is None


def test_wrong_token_type():
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "123",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "refresh",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(token) is None


def test_invalid_customer_id():
    token = create_access_token(customer_id=0)

    assert decode_access_token(token) is None
