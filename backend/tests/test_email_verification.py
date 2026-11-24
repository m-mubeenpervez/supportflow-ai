"""No-network tests for verification security primitives."""

from datetime import datetime, timedelta, timezone

import pytest

from app.email_verification import (
    TOKEN_TTL,
    RESEND_COOLDOWN,
    hash_token,
    issue_challenge,
    is_token_usable,
    resend_allowed,
)

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def test_token_is_unique_and_correctly_formatted():
    first = issue_challenge(NOW)
    second = issue_challenge(NOW)

    assert len(first.raw_token) == 43
    assert first.raw_token != second.raw_token
    assert first.token_hash != second.token_hash


def test_only_hash_is_suitable_for_database_storage():
    challenge = issue_challenge(NOW)

    assert len(challenge.token_hash) == 64
    assert challenge.token_hash == hash_token(challenge.raw_token)
    assert challenge.raw_token != challenge.token_hash


def test_token_expires_after_30_minutes():
    challenge = issue_challenge(NOW)

    assert TOKEN_TTL == timedelta(minutes=30)
    assert challenge.expires_at == NOW + TOKEN_TTL
    assert is_token_usable(
        challenge.expires_at,
        now=NOW + timedelta(minutes=29),
    )


def test_expired_token_rejected_at_boundary():
    challenge = issue_challenge(NOW)

    assert not is_token_usable(
        challenge.expires_at,
        now=NOW + timedelta(minutes=30),
    )


def test_consumed_token_rejected():
    challenge = issue_challenge(NOW)

    assert not is_token_usable(
        challenge.expires_at,
        consumed_at=NOW + timedelta(minutes=1),
        now=NOW + timedelta(minutes=2),
    )


def test_resend_cooldown():
    assert RESEND_COOLDOWN == timedelta(seconds=60)
    assert not resend_allowed(
        NOW,
        now=NOW + timedelta(seconds=59),
    )
    assert resend_allowed(
        NOW,
        now=NOW + timedelta(seconds=60),
    )


def test_first_send_is_allowed():
    assert resend_allowed(None, now=NOW)


@pytest.mark.parametrize(
    "value",
    ["", "invalid", "a" * 42, "a" * 44, "a" * 42 + "!", None],
)
def test_invalid_token_format_rejected(value):
    with pytest.raises(ValueError):
        hash_token(value)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        issue_challenge(datetime(2026, 11, 17))


def test_non_utc_datetime_rejected():
    from datetime import timezone as tz

    offset = tz(timedelta(hours=5))

    with pytest.raises(ValueError):
        issue_challenge(
            datetime(2026, 11, 17, tzinfo=offset)
        )
