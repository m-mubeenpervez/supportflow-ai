
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from .config import settings


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Convert a plain password into a secure Argon2 hash."""
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Check a password against its stored hash."""
    try:
        return password_hasher.verify(
            plain_password,
            hashed_password,
        )
    except (ValueError, TypeError):
        return False


def create_access_token(customer_id: int, session_version: int = 0) -> str:
    """Create a signed, time-limited customer JWT."""
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT secret is not configured")

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(customer_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        ),
        "type": "access",
        "sv": session_version,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> int | None:
    """Validate a customer JWT and return its customer ID."""
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT secret is not configured")

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "iat", "exp", "type"],
            },
        )

        if payload.get("type") != "access":
            return None

        subject = payload.get("sub")

        if not isinstance(subject, str):
            return None

        customer_id = int(subject)

        if customer_id <= 0:
            return None

        return customer_id

    except (InvalidTokenError, ValueError, TypeError):
        return None


def decode_access_token_version(token: str) -> int | None:
    """Validate token and retrieve its session version."""
    if decode_access_token(token) is None:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "iat", "exp", "type"],
            },
        )

        version = payload.get("sv", 0)

        if type(version) is not int or version < 0:
            return None

        return version

    except (InvalidTokenError, ValueError, TypeError):
        return None
