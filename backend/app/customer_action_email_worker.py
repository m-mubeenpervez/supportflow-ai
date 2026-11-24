"""Explicit, bounded account-notice delivery integrated with email_runner.

Uses PostgreSQL SKIP LOCKED and a claim token; no work starts on import.
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
class AccountNoticeJob:
    id: int
    customer_id: int
    claim_token: str
    recipient_email: str
    subject: str
    body: str
    attempts: int


async def recover_exhausted(session_factory=Session):
    if not settings.email_delivery_enabled:
        return 0
    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(text("""
                UPDATE customer_action_email_outbox
                   SET status='failed', claim_token=NULL,
                       lease_expires_at=NULL,
                       recipient_email='redacted-' || customer_id || '@deleted.invalid',
                       last_error='Worker lease expired'
                 WHERE status='processing'
                   AND lease_expires_at<=clock_timestamp()
                   AND attempts>=:max_attempts
            """), {"max_attempts": settings.email_max_attempts})
            return result.rowcount


async def claim_account_notice(session_factory=Session):
    if not settings.email_delivery_enabled:
        return None
    if settings.email_max_attempts < 1:
        raise RuntimeError("Invalid email retry limit")
    token = str(uuid.uuid4())
    lease_seconds = max(900, settings.email_smtp_timeout_seconds * 4)
    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(text("""
                WITH candidate AS (
                    SELECT id FROM customer_action_email_outbox
                    WHERE attempts < :max_attempts
                      AND ((status IN ('pending','retry') AND next_attempt_at<=clock_timestamp())
                        OR (status='processing' AND lease_expires_at<=clock_timestamp()))
                    ORDER BY next_attempt_at, id
                    LIMIT 1 FOR UPDATE SKIP LOCKED
                )
                UPDATE customer_action_email_outbox AS n
                   SET status='processing', attempts=n.attempts+1,
                       claim_token=:token,
                       lease_expires_at=NOW()+make_interval(secs=>:lease_seconds)
                  FROM candidate WHERE n.id=candidate.id
                RETURNING n.id,n.customer_id,n.claim_token,n.recipient_email,
                          n.subject,n.body,n.attempts
            """), {
                "max_attempts": settings.email_max_attempts,
                "token": token,
                "lease_seconds": lease_seconds,
            })
            row = result.mappings().one_or_none()
            return AccountNoticeJob(**dict(row)) if row is not None else None


async def finish_notice(job, *, status, error=None, session_factory=Session):
    values = {
        "id": job.id, "token": job.claim_token, "status": status,
        "next_at": datetime.now(timezone.utc),
        "error": None if error is None else type(error).__name__[:100],
        "is_sent": status == "sent",
    }
    if status in ("failed", "retry"):
        decision = after_delivery_failure(
            previous_attempts=job.attempts - 1,
            max_attempts=settings.email_max_attempts,
            now=datetime.now(timezone.utc),
        )
        values["status"] = decision.status
        values["next_at"] = decision.next_attempt_at or values["next_at"]
    redact = values["status"] in ("sent", "failed")
    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(text("""
                UPDATE customer_action_email_outbox
                   SET status=:status,
                       next_attempt_at=:next_at,
                       sent_at=CASE WHEN :is_sent THEN clock_timestamp() ELSE sent_at END,
                       recipient_email=CASE WHEN :redact
                         THEN 'redacted-' || customer_id || '@deleted.invalid'
                         ELSE recipient_email END,
                       claim_token=NULL, lease_expires_at=NULL,
                       last_error=:error
                 WHERE id=:id AND status='processing'
                   AND claim_token=:token AND lease_expires_at>clock_timestamp()
            """), {**values, "redact": redact})
            return result.rowcount == 1


async def process_one_account_notice(session_factory=Session, sender=None):
    if not settings.email_delivery_enabled:
        return "disabled"
    await recover_exhausted(session_factory)
    job = await claim_account_notice(session_factory)
    if job is None:
        return "empty"
    try:
        await (sender or send_email)(job.recipient_email, job.subject, job.body)
    except Exception as exc:
        changed = await finish_notice(job, status="retry", error=exc, session_factory=session_factory)
        if not changed:
            return "ownership_lost"
        return "failed" if job.attempts >= settings.email_max_attempts else "retry"
    changed = await finish_notice(job, status="sent", session_factory=session_factory)
    return "sent" if changed else "ownership_lost"
