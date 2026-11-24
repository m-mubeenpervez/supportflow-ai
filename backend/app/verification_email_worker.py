"""PostgreSQL claim service for verification email delivery.

No SMTP, decryption, logging of secrets or automatic worker loop.
The claim transaction finishes before any eventual SMTP send.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from .config import settings
from .db import Session


@dataclass(frozen=True)
class ClaimedVerificationEmail:
    id: int
    customer_id: int
    token_hash: str
    encrypted_token: str
    expires_at: datetime
    claim_token: str
    lease_expires_at: datetime
    attempts: int


async def claim_verification_email(
    session_factory=Session,
    *,
    allow_mock_delivery: bool = False,
) -> ClaimedVerificationEmail | None:
    """Atomically claim one currently eligible verification email.

    The mock override is explicit and intended only for
    isolated tests. Never use it for production execution.

    PostgreSQL row locking prevents simultaneous claims.
    A separate pre-send check is still required before SMTP.
    """

    if not settings.email_delivery_enabled and not allow_mock_delivery:
        return None

    maximum = settings.email_max_attempts
    timeout = settings.email_smtp_timeout_seconds

    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum < 1
    ):
        raise RuntimeError("Invalid email retry limit")

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or timeout < 1
    ):
        raise RuntimeError("Invalid SMTP timeout")

    lease_seconds = max(900, timeout * 4)
    owner = str(uuid.uuid4())

    async with session_factory() as db:
        async with db.begin():
            result = await db.execute(
                text("""
                    WITH candidate AS (
                        SELECT e.id
                        FROM verification_email_outbox AS e
                        JOIN customers AS c
                          ON c.id = e.customer_id
                        JOIN email_verification_tokens AS v
                          ON v.customer_id = e.customer_id
                        WHERE c.email_verified_at IS NULL
                          AND v.consumed_at IS NULL
                          AND v.expires_at > NOW()
                          AND e.expires_at > NOW()
                          AND e.expires_at = v.expires_at
                          AND e.token_hash = v.token_hash
                          AND e.attempts < :maximum
                          AND (
                              (
                                  e.status = 'pending'
                                  AND e.next_attempt_at <= NOW()
                              )
                              OR (
                                  e.status = 'processing'
                                  AND e.lease_expires_at <= NOW()
                              )
                          )
                        ORDER BY e.next_attempt_at, e.id
                        LIMIT 1
                        FOR UPDATE OF e SKIP LOCKED
                    )
                    UPDATE verification_email_outbox AS e
                    SET status = 'processing',
                        attempts = e.attempts + 1,
                        claim_token = :owner,
                        lease_expires_at =
                            NOW() + make_interval(
                                secs => :lease_seconds
                            )
                    FROM candidate
                    WHERE e.id = candidate.id
                    RETURNING
                        e.id,
                        e.customer_id,
                        e.token_hash,
                        e.encrypted_token,
                        e.expires_at,
                        e.claim_token,
                        e.lease_expires_at,
                        e.attempts
                """),
                {
                    "maximum": maximum,
                    "owner": owner,
                    "lease_seconds": lease_seconds,
                },
            )

            row = result.mappings().one_or_none()

            if row is None:
                return None

            return ClaimedVerificationEmail(**dict(row))
