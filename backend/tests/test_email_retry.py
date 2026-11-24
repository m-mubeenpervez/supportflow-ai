"""Unit tests for email retry decisions."""

from datetime import datetime, timedelta, timezone

import pytest

from app.email_retry import (
    after_delivery_failure,
    retry_delay_seconds,
)


@pytest.mark.parametrize(
    ("attempt", "seconds"),
    [
        (1, 60),
        (2, 120),
        (3, 240),
        (4, 480),
        (5, 960),
        (20, 3600),
    ],
)
def test_exponential_delay(attempt, seconds):
    assert retry_delay_seconds(attempt) == seconds


def test_failure_schedules_retry():
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)

    decision = after_delivery_failure(
        previous_attempts=0,
        max_attempts=5,
        now=now,
    )

    assert decision.status == "pending"
    assert decision.attempts == 1
    assert decision.next_attempt_at == now + timedelta(minutes=1)


def test_fifth_failure_stops_retries():
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)

    decision = after_delivery_failure(
        previous_attempts=4,
        max_attempts=5,
        now=now,
    )

    assert decision.status == "failed"
    assert decision.attempts == 5
    assert decision.next_attempt_at is None


def test_historical_excess_attempts_stay_failed():
    decision = after_delivery_failure(
        previous_attempts=9,
        max_attempts=5,
    )

    assert decision.status == "failed"
    assert decision.attempts == 10


@pytest.mark.parametrize("attempts", [-1, 0, True, 1.5])
def test_invalid_retry_delay_attempts(attempts):
    with pytest.raises(ValueError):
        retry_delay_seconds(attempts)


def test_invalid_retry_configuration():
    with pytest.raises(ValueError):
        after_delivery_failure(
            previous_attempts=0,
            max_attempts=0,
        )


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        after_delivery_failure(
            previous_attempts=0,
            max_attempts=5,
            now=datetime(2026, 11, 17),
        )
