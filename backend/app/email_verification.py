"""Security primitives for customer email verification.

Pure functions only: no database, SMTP, or external API calls.
Raw verification tokens must never be logged or persisted.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TOKEN_TTL = timedelta(minutes=30)
RESEND_COOLDOWN = timedelta(seconds=60)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


@dataclass(frozen=True)
class VerificationChallenge:
    raw_token: str
    token_hash: str
    expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")

    if value.utcoffset() != timedelta(0):
        raise ValueError("UTC datetime required")

    return value


def hash_token(raw_token: str) -> str:
    """Hash a correctly formatted URL-safe verification token."""

    if (
        not isinstance(raw_token, str)
        or _TOKEN_PATTERN.fullmatch(raw_token) is None
    ):
        raise ValueError("Invalid verification token format")

    return hashlib.sha256(
        raw_token.encode("ascii")
    ).hexdigest()


def issue_challenge(
    now: datetime | None = None,
) -> VerificationChallenge:
    """Generate a cryptographically random 256-bit challenge."""

    current = require_utc(now or utc_now())
    raw_token = secrets.token_urlsafe(32)

    return VerificationChallenge(
        raw_token=raw_token,
        token_hash=hash_token(raw_token),
        expires_at=current + TOKEN_TTL,
    )


def is_token_usable(
    expires_at: datetime,
    consumed_at: datetime | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """Expired and already consumed tokens are unusable."""

    current = require_utc(now or utc_now())
    expiry = require_utc(expires_at)

    if consumed_at is not None:
        require_utc(consumed_at)
        return False

    return current < expiry


def resend_allowed(
    last_sent_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether the minimum resend cooldown has elapsed."""

    current = require_utc(now or utc_now())

    if last_sent_at is None:
        return True

    previous = require_utc(last_sent_at)

    return current >= previous + RESEND_COOLDOWN
