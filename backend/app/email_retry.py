"""Pure retry-decision helpers for email outbox delivery."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class RetryDecision:
    status: str
    attempts: int
    next_attempt_at: datetime | None


def retry_delay_seconds(attempts: int) -> int:
    """Bounded exponential delay after a failed send."""

    if not isinstance(attempts, int) or isinstance(attempts, bool):
        raise ValueError("Attempts must be an integer")

    if attempts < 1:
        raise ValueError("Attempts must be positive")

    # Cap at 1 hour, even for unusually high attempt counts.
    return min(60 * (2 ** min(attempts - 1, 6)), 3600)


def after_delivery_failure(
    *,
    previous_attempts: int,
    max_attempts: int,
    now: datetime | None = None,
) -> RetryDecision:
    """Return the next queue state without writing to the DB."""

    if not isinstance(previous_attempts, int) or isinstance(previous_attempts, bool):
        raise ValueError("Invalid previous attempts")

    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
        raise ValueError("Invalid maximum attempts")

    if previous_attempts < 0 or max_attempts < 1:
        raise ValueError("Invalid retry configuration")

    current_time = now or datetime.now(timezone.utc)

    if current_time.tzinfo is None:
        raise ValueError("Timestamp must include timezone")

    attempts = previous_attempts + 1

    if attempts >= max_attempts:
        return RetryDecision(
            status="failed",
            attempts=attempts,
            next_attempt_at=None,
        )

    return RetryDecision(
        status="pending",
        attempts=attempts,
        next_attempt_at=(
            current_time
            + timedelta(seconds=retry_delay_seconds(attempts))
        ),
    )
