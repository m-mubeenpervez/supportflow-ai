"""Fail-closed runtime configuration for verification emails.

Never log, return through HTTP, or print the encryption key.
"""

from dataclasses import dataclass

from cryptography.fernet import Fernet

from .config import settings
from .verification_delivery_processor import (
    build_verification_url,
)


@dataclass(frozen=True)
class VerificationEmailRuntimeConfig:
    encryption_key: str
    base_url: str


def get_verification_email_config(
    config=None,
) -> VerificationEmailRuntimeConfig:
    """Validate runtime settings before queuing any challenge."""

    config = settings if config is None else config

    key = getattr(
        config,
        "verification_email_encryption_key",
        "",
    )
    base_url = getattr(
        config,
        "verification_email_base_url",
        "",
    )

    if not isinstance(key, str) or not key:
        raise RuntimeError(
            "Verification email encryption key is not configured"
        )

    try:
        Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise RuntimeError(
            "Invalid verification email encryption key"
        ) from exc

    if not isinstance(base_url, str) or not base_url:
        raise RuntimeError(
            "Verification email base URL is not configured"
        )

    try:
        build_verification_url(base_url, "A" * 43)
    except ValueError as exc:
        raise RuntimeError(
            "Invalid verification email base URL"
        ) from exc

    return VerificationEmailRuntimeConfig(
        encryption_key=key,
        base_url=base_url,
    )
