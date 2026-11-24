"""Bounded email worker execution and aggregate monitoring.

No background task starts automatically.
"""

from dataclasses import dataclass

from .config import settings
from .db import Session
from .email_worker import process_one
from .customer_action_email_worker import process_one_account_notice


@dataclass(frozen=True)
class BatchSummary:
    processed: int
    sent: int
    retry: int
    failed: int
    ownership_lost: int
    disabled: bool


async def run_batch(
    session_factory=Session,
    *,
    processor=None,
    sender=None,
    batch_size=None,
) -> BatchSummary:
    """Process a bounded batch, without exposing email contents."""

    if not settings.email_delivery_enabled:
        return BatchSummary(0, 0, 0, 0, 0, True)

    limit = (
        settings.email_worker_batch_size
        if batch_size is None
        else batch_size
    )

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 100
    ):
        raise ValueError("Invalid email batch size")

    process = processor if processor is not None else process_one

    counts = {
        "sent": 0,
        "retry": 0,
        "failed": 0,
        "ownership_lost": 0,
    }

    processed = 0

    for _ in range(limit):
        # Recheck configuration before each attempt.
        if not settings.email_delivery_enabled:
            return BatchSummary(
                processed=processed,
                disabled=True,
                **counts,
            )

        result = await process(
            session_factory=session_factory,
            sender=sender,
        )
        # When the ticket email queue is empty, also drain the independent
        # account-action outbox using the same opt-in SMTP worker.
        if result == "empty" and processor is None:
            result = await process_one_account_notice(
                session_factory=session_factory, sender=sender,
            )

        if result == "empty":
            break

        if result == "disabled":
            return BatchSummary(
                processed=processed,
                disabled=True,
                **counts,
            )

        if result not in counts:
            raise RuntimeError(
                "Unexpected email worker result"
            )

        counts[result] += 1
        processed += 1

    return BatchSummary(
        processed=processed,
        disabled=False,
        **counts,
    )
