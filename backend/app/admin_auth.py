"""JWT primitives for administrator sessions.

Admin identity and permissions must also be checked against
the database by protected API dependencies.
"""

from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError

from .config import settings


ADMIN_TOKEN_TYPE = "admin_access"
ADMIN_TOKEN_LIFETIME_MINUTES = 15


def create_admin_access_token(
    admin_id: int,
    session_version: int,
) -> str:
    """Create a short-lived, purpose-specific admin JWT."""

    if not settings.jwt_secret_key:
        raise RuntimeError("JWT secret is not configured")

    if type(admin_id) is not int or admin_id <= 0:
        raise ValueError("Invalid admin ID")

    if type(session_version) is not int or session_version < 0:
        raise ValueError("Invalid session version")

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(admin_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=ADMIN_TOKEN_LIFETIME_MINUTES
        ),
        "type": ADMIN_TOKEN_TYPE,
        "sv": session_version,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_admin_access_token(
    token: str,
) -> tuple[int, int] | None:
    """Validate an admin JWT and return ID and session version."""

    if not settings.jwt_secret_key:
        raise RuntimeError("JWT secret is not configured")

    if not isinstance(token, str) or not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": [
                    "sub", "iat", "exp", "type", "sv"
                ],
            },
        )

        if payload.get("type") != ADMIN_TOKEN_TYPE:
            return None

        subject = payload.get("sub")
        version = payload.get("sv")

        if not isinstance(subject, str):
            return None

        if (
            not subject.isascii()
            or not subject.isdecimal()
        ):
            return None

        admin_id = int(subject)

        if admin_id <= 0:
            return None

        if type(version) is not int or version < 0:
            return None

        return admin_id, version

    except (InvalidTokenError, ValueError, TypeError):
        return None
