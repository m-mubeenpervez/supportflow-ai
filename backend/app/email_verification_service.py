"""Transactional customer email verification service.

Call these helpers inside the caller's database transaction.
They flush changes but NEVER commit, send email or log tokens.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .email_verification import (
    hash_token,
    issue_challenge,
    is_token_usable,
    require_utc,
    resend_allowed,
    utc_now,
)
from .models import Customer, EmailVerificationToken


class VerificationCooldownError(ValueError):
    """Verification token was requested too recently."""


class AlreadyVerifiedError(ValueError):
    """Customer email is already verified."""


async def issue_verification_token(
    db: AsyncSession,
    *,
    customer_id: int,
    now=None,
):
    """Issue or rotate a customer's single verification token.

    Returns a challenge containing the raw token.
    Caller must enqueue the email in the SAME transaction.
    Never return the raw token in an HTTP API response.

    Locking the customer row serializes concurrent requests.
    """

    current = require_utc(now or utc_now())

    customer = await db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .with_for_update()
    )

    if customer is None:
        raise ValueError("Customer does not exist")

    if customer.email_verified_at is not None:
        raise AlreadyVerifiedError(
            "Customer email is already verified"
        )

    record = await db.scalar(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.customer_id == customer_id
        )
        .with_for_update()
    )

    if (
        record is not None
        and not resend_allowed(
            record.last_sent_at,
            now=current,
        )
    ):
        raise VerificationCooldownError(
            "Verification resend cooldown is active"
        )

    challenge = issue_challenge(current)

    if record is None:
        record = EmailVerificationToken(
            customer_id=customer.id,
            token_hash=challenge.token_hash,
            expires_at=challenge.expires_at,
            last_sent_at=current,
            created_at=current,
            consumed_at=None,
        )
        db.add(record)
    else:
        # A resend invalidates the previous verification link.
        record.token_hash = challenge.token_hash
        record.expires_at = challenge.expires_at
        record.last_sent_at = current
        record.created_at = current
        record.consumed_at = None

    await db.flush()
    return challenge


async def consume_verification_token(
    db: AsyncSession,
    *,
    raw_token: str,
    now=None,
) -> bool:
    """Atomically consume a valid challenge and verify its owner.

    Returns False for invalid, expired, consumed or rotated
    challenges. No automatic commit is performed.
    """

    current = require_utc(now or utc_now())

    try:
        digest = hash_token(raw_token)
    except ValueError:
        return False

    # Read ID first, without locking, to establish consistent
    # lock order: Customer -> EmailVerificationToken.
    owner_id = await db.scalar(
        select(EmailVerificationToken.customer_id)
        .where(EmailVerificationToken.token_hash == digest)
    )

    if owner_id is None:
        return False

    customer = await db.scalar(
        select(Customer)
        .where(Customer.id == owner_id)
        .with_for_update()
    )

    if customer is None:
        return False

    record = await db.scalar(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.customer_id == owner_id
        )
        .with_for_update()
    )

    if record is None:
        return False

    # Recheck the hash after locking to reject token rotation
    # that happened while this request was waiting.
    if not secrets.compare_digest(record.token_hash, digest):
        return False

    if not is_token_usable(
        record.expires_at,
        record.consumed_at,
        now=current,
    ):
        return False

    if customer.email_verified_at is not None:
        return False

    customer.email_verified_at = current
    record.consumed_at = current

    await db.flush()
    return True
