"""Fail-closed verification email delivery eligibility checks.

Pure functions. No SMTP, database writes, or logging.
The database worker must independently enforce claim ownership.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime

from .email_verification import (
    hash_token,
    is_token_usable,
    require_utc,
    utc_now,
)
from .verification_email_crypto import decrypt_token


@dataclass(frozen=True)
class DeliveryEligibility:
    allowed: bool
    reason: str


def check_delivery_eligibility(
    *,
    customer_verified_at: datetime | None,
    active_token_hash: str | None,
    token_expires_at: datetime,
    token_consumed_at: datetime | None,
    queue_token_hash: str,
    queue_expires_at: datetime,
    queue_status: str,
    claim_token: str | None,
    expected_claim_token: str,
    lease_expires_at: datetime | None,
    now: datetime | None = None,
) -> DeliveryEligibility:
    """Decide whether a claimed verification job is still valid."""

    current = require_utc(now or utc_now())

    if customer_verified_at is not None:
        return DeliveryEligibility(False, "already_verified")

    if queue_status != "processing":
        return DeliveryEligibility(False, "not_processing")

    if (
        not claim_token
        or not expected_claim_token
        or not secrets.compare_digest(
            claim_token,
            expected_claim_token,
        )
    ):
        return DeliveryEligibility(False, "claim_mismatch")

    if (
        lease_expires_at is None
        or require_utc(lease_expires_at) <= current
    ):
        return DeliveryEligibility(False, "lease_expired")

    if (
        not isinstance(active_token_hash, str)
        or not isinstance(queue_token_hash, str)
        or len(active_token_hash) != 64
        or len(queue_token_hash) != 64
        or not secrets.compare_digest(
            active_token_hash,
            queue_token_hash,
        )
    ):
        return DeliveryEligibility(False, "token_rotated")

    if not is_token_usable(
        token_expires_at,
        token_consumed_at,
        now=current,
    ):
        return DeliveryEligibility(False, "token_inactive")

    if require_utc(queue_expires_at) <= current:
        return DeliveryEligibility(False, "queue_expired")

    if require_utc(queue_expires_at) != require_utc(
        token_expires_at
    ):
        return DeliveryEligibility(False, "expiry_mismatch")

    return DeliveryEligibility(True, "eligible")


def decrypt_eligible_token(
    *,
    encrypted_token: str,
    encryption_key: str,
    expected_token_hash: str,
) -> str:
    """Decrypt a validated job and verify its token hash.

    Call only after eligibility checks have passed.
    Never persist or log the returned raw token.
    """

    raw_token = decrypt_token(
        encrypted_token,
        encryption_key,
    )

    calculated_hash = hash_token(raw_token)

    if not (
        isinstance(expected_token_hash, str)
        and len(expected_token_hash) == 64
        and secrets.compare_digest(
            calculated_hash,
            expected_token_hash,
        )
    ):
        raise ValueError(
            "Verification email token consistency failure"
        )

    return raw_token
