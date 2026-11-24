"""Safe finalization of verification email worker claims.

Only the current, unexpired claim owner may update the queue.
No email sending, decryption, raw token logging or auto-start.
"""

from datetime import datetime, timezone

from sqlalchemy import text

from .config import settings
from .db import Session
from .email_retry import after_delivery_failure


# Shared guard prevents stale workers from overwriting a
# replacement token or another worker's active claim.
_CLAIM_GUARD = """
    id = :id
    AND customer_id = :customer_id
    AND token_hash = :token_hash
    AND status = 'processing'
    AND claim_token = :claim_token
    AND lease_expires_at > NOW()
"""


def _claim_params(job) -> dict:
    """Build parameters without exposing encrypted content."""

    if (
        not isinstance(job.id, int)
        or isinstance(job.id, bool)
        or job.id <= 0
        or not isinstance(job.customer_id, int)
        or isinstance(job.customer_id, bool)
        or job.customer_id <= 0
        or not isinstance(job.token_hash, str)
        or len(job.token_hash) != 64
        or not isinstance(job.claim_token, str)
        or not job.claim_token
    ):
        raise ValueError("Invalid verification worker claim")

    return {
        "id": job.id,
        "customer_id": job.customer_id,
        "token_hash": job.token_hash,
        "claim_token": job.claim_token,
    }


async def mark_verification_sent(
    job,
    session_factory=Session,
) -> bool:
    """Record SMTP acceptance for the current claim owner."""

    params = _claim_params(job)

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    """
                    UPDATE verification_email_outbox
                    SET status = 'sent',
                        sent_at = NOW(),
                        claim_token = NULL,
                        lease_expires_at = NULL,
                        last_error = NULL
                    WHERE
                    """ + _CLAIM_GUARD
                ),
                params,
            )

            return result.rowcount == 1


async def mark_verification_failed(
    job,
    error: Exception,
    session_factory=Session,
) -> str:
    """Retry or fail a job without storing SMTP error details.

    Returns 'retry', 'failed', or 'ownership_lost'.
    """

    params = _claim_params(job)

    maximum = settings.email_max_attempts

    decision = after_delivery_failure(
        previous_attempts=job.attempts - 1,
        max_attempts=maximum,
        now=datetime.now(timezone.utc),
    )

    # Exception messages can contain recipient addresses,
    # SMTP responses or credentials. Store only the type.
    error_label = type(error).__name__[:100]

    params.update({
        "status": decision.status,
        "next_attempt": (
            decision.next_attempt_at
            or datetime.now(timezone.utc)
        ),
        "error_label": error_label,
    })

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    """
                    UPDATE verification_email_outbox
                    SET status = :status,
                        next_attempt_at = :next_attempt,
                        claim_token = NULL,
                        lease_expires_at = NULL,
                        last_error = :error_label
                    WHERE
                    """ + _CLAIM_GUARD
                ),
                params,
            )

            if result.rowcount != 1:
                return "ownership_lost"

    return decision.status if decision.status == "failed" else "retry"


async def retire_verification_claim(
    job,
    session_factory=Session,
) -> bool:
    """Retire a job that failed delivery eligibility checks.

    This is a terminal state for the current challenge.
    A future resend can create a fresh pending challenge.
    """

    params = _claim_params(job)

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    """
                    UPDATE verification_email_outbox
                    SET status = 'failed',
                        claim_token = NULL,
                        lease_expires_at = NULL,
                        last_error = 'Verification job ineligible'
                    WHERE
                    """ + _CLAIM_GUARD
                ),
                params,
            )

            return result.rowcount == 1
