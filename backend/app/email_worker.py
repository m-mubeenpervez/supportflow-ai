"""PostgreSQL-backed email outbox processor.

No worker starts on import. Delivery remains opt-in.
SMTP acceptance is not proof of inbox delivery.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from .config import settings
from .db import Session
from .email_retry import after_delivery_failure
from .email_transport import send_email


@dataclass(frozen=True)
class ClaimedEmail:
    id: int
    claim_token: str
    recipient_email: str
    subject: str
    body: str
    attempts: int


async def recover_exhausted(session_factory=Session) -> int:
    """Retire expired claims that exhausted the attempt limit."""

    if not settings.email_delivery_enabled:
        return 0

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text("""
                    UPDATE email_outbox
                    SET status = 'failed',
                        claim_token = NULL,
                        lease_expires_at = NULL,
                        last_error = 'Worker lease expired'
                    WHERE status = 'processing'
                      AND lease_expires_at <= NOW()
                      AND attempts >= :maximum
                """),
                {"maximum": settings.email_max_attempts},
            )
            return result.rowcount


async def claim_email(session_factory=Session):
    """Atomically claim one due message.

    PostgreSQL SKIP LOCKED prevents concurrent claims
    of the same row. SMTP runs after this transaction.
    """

    if not settings.email_delivery_enabled:
        return None

    if settings.email_max_attempts < 1:
        raise RuntimeError("Invalid email retry limit")

    token = str(uuid.uuid4())

    # Larger than the normal SMTP timeout. An unexpectedly
    # long SMTP operation can still outlive this lease.
    lease_seconds = max(
        900,
        settings.email_smtp_timeout_seconds * 4,
    )

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text("""
                    WITH candidate AS (
                        SELECT id
                        FROM email_outbox
                        WHERE attempts < :maximum
                          AND (
                            (
                              status = 'pending'
                              AND next_attempt_at <= NOW()
                            )
                            OR (
                              status = 'processing'
                              AND lease_expires_at <= NOW()
                            )
                          )
                        ORDER BY next_attempt_at, id
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE email_outbox AS e
                    SET status = 'processing',
                        attempts = e.attempts + 1,
                        claim_token = :token,
                        lease_expires_at =
                            NOW() + make_interval(
                                secs => :lease_seconds
                            )
                    FROM candidate
                    WHERE e.id = candidate.id
                    RETURNING
                        e.id,
                        e.claim_token,
                        e.recipient_email,
                        e.subject,
                        e.body,
                        e.attempts
                """),
                {
                    "maximum": settings.email_max_attempts,
                    "token": token,
                    "lease_seconds": lease_seconds,
                },
            )

            row = result.mappings().one_or_none()

            if row is None:
                return None

            return ClaimedEmail(**dict(row))


async def mark_sent(job, session_factory=Session) -> bool:
    """Only the current claim owner may record SMTP acceptance."""

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text("""
                    UPDATE email_outbox
                    SET status = 'sent',
                        sent_at = NOW(),
                        claim_token = NULL,
                        lease_expires_at = NULL,
                        last_error = NULL
                    WHERE id = :id
                      AND status = 'processing'
                      AND claim_token = :token
                      AND lease_expires_at > NOW()
                """),
                {
                    "id": job.id,
                    "token": job.claim_token,
                },
            )
            return result.rowcount == 1


async def mark_failed(
    job,
    error,
    session_factory=Session,
) -> bool:
    """Schedule retry or record a terminal failure."""

    decision = after_delivery_failure(
        previous_attempts=job.attempts - 1,
        max_attempts=settings.email_max_attempts,
        now=datetime.now(timezone.utc),
    )

    # Do not store raw SMTP exception text. It can contain
    # recipient addresses or sensitive server responses.
    error_label = type(error).__name__[:100]

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text("""
                    UPDATE email_outbox
                    SET status = :status,
                        next_attempt_at = :next_attempt,
                        claim_token = NULL,
                        lease_expires_at = NULL,
                        last_error = :error
                    WHERE id = :id
                      AND status = 'processing'
                      AND claim_token = :token
                      AND lease_expires_at > NOW()
                """),
                {
                    "id": job.id,
                    "token": job.claim_token,
                    "status": decision.status,
                    # Column is NOT NULL in the existing DB.
                    "next_attempt": (
                        decision.next_attempt_at
                        or datetime.now(timezone.utc)
                    ),
                    "error": error_label,
                },
            )
            return result.rowcount == 1


async def process_one(
    session_factory=Session,
    sender=None,
):
    """Process at most one email, without starting a loop.

    Returns disabled, empty, sent, retry, failed, or
    ownership_lost. No recipient details are returned.
    """

    if not settings.email_delivery_enabled:
        return "disabled"

    await recover_exhausted(session_factory)

    job = await claim_email(session_factory)

    if job is None:
        return "empty"

    delivery_sender = sender or send_email

    try:
        await delivery_sender(
            job.recipient_email,
            job.subject,
            job.body,
        )
    except Exception as exc:
        updated = await mark_failed(
            job,
            exc,
            session_factory,
        )

        if not updated:
            return "ownership_lost"

        return (
            "failed"
            if job.attempts >= settings.email_max_attempts
            else "retry"
        )

    updated = await mark_sent(job, session_factory)

    return "sent" if updated else "ownership_lost"
