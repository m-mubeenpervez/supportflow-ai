"""Transactional encrypted verification-email queue.

The caller owns the transaction and must commit it.
No SMTP calls, background jobs, or raw-token logging.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .email_verification import (
    require_utc,
    utc_now,
)
from .email_verification_service import (
    issue_verification_token,
)
from .models import (
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from .verification_email_crypto import encrypt_token


@dataclass(frozen=True)
class VerificationQueueResult:
    customer_id: int
    outbox_id: int
    expires_at: datetime


async def queue_verification_email(
    db: AsyncSession,
    *,
    customer_id: int,
    encryption_key: str,
    now: datetime | None = None,
) -> VerificationQueueResult:
    """Issue a challenge and stage an encrypted delivery job.

    Must be called inside a transaction. This function does not
    commit. A resend replaces the customer's previous queued
    token; worker-side freshness checks are still required.
    """

    current = require_utc(now or utc_now())

    if (
        not isinstance(customer_id, int)
        or isinstance(customer_id, bool)
        or customer_id <= 0
    ):
        raise ValueError("Invalid customer ID")

    if (
        not isinstance(encryption_key, str)
        or not encryption_key
    ):
        raise ValueError("Encryption key is required")

    # Locks the customer row and enforces verification status
    # and the 60-second resend cooldown.
    challenge = await issue_verification_token(
        db,
        customer_id=customer_id,
        now=current,
    )

    ciphertext = encrypt_token(
        challenge.raw_token,
        encryption_key,
    )

    # The existing challenge is locked and flushed by
    # issue_verification_token().
    token_record = await db.scalar(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.customer_id == customer_id
        )
    )

    if (
        token_record is None
        or token_record.token_hash != challenge.token_hash
    ):
        raise RuntimeError(
            "Verification token consistency check failed"
        )

    # Customer-row lock serializes concurrent queue requests.
    record = await db.scalar(
        select(VerificationEmailOutbox)
        .where(
            VerificationEmailOutbox.customer_id == customer_id
        )
        .with_for_update()
    )

    if record is None:
        record = VerificationEmailOutbox(
            customer_id=customer_id,
            token_hash=challenge.token_hash,
            encrypted_token=ciphertext,
            expires_at=challenge.expires_at,
            status="pending",
            attempts=0,
            next_attempt_at=current,
            created_at=current,
        )
        db.add(record)

    else:
        # Replace any older pending/sent/failed challenge.
        # A previous worker may already be in flight;
        # delivery must independently check token freshness.
        record.token_hash = challenge.token_hash
        record.encrypted_token = ciphertext
        record.expires_at = challenge.expires_at
        record.status = "pending"
        record.attempts = 0
        record.next_attempt_at = current
        record.claim_token = None
        record.lease_expires_at = None
        record.last_error = None
        record.sent_at = None
        record.created_at = current

    await db.flush()

    return VerificationQueueResult(
        customer_id=customer_id,
        outbox_id=record.id,
        expires_at=challenge.expires_at,
    )
