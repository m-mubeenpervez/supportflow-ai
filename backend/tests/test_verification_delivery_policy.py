"""Unit tests for verification delivery eligibility."""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from app.email_verification import issue_challenge
from app.verification_delivery_policy import (
    check_delivery_eligibility,
    decrypt_eligible_token,
)
from app.verification_email_crypto import encrypt_token


NOW = datetime(
    2026, 11, 18, 12, 0, tzinfo=timezone.utc
)


def valid_job():
    challenge = issue_challenge(NOW)

    return {
        "customer_verified_at": None,
        "active_token_hash": challenge.token_hash,
        "token_expires_at": challenge.expires_at,
        "token_consumed_at": None,
        "queue_token_hash": challenge.token_hash,
        "queue_expires_at": challenge.expires_at,
        "queue_status": "processing",
        "claim_token": "worker-claim-1",
        "expected_claim_token": "worker-claim-1",
        "lease_expires_at": NOW + timedelta(minutes=15),
        "now": NOW,
    }


def check(**changes):
    job = valid_job()
    job.update(changes)

    return check_delivery_eligibility(**job)


def test_valid_job_is_eligible():
    assert check().allowed is True


def test_verified_customer_rejected():
    result = check(customer_verified_at=NOW)

    assert not result.allowed
    assert result.reason == "already_verified"


def test_pending_job_rejected():
    assert not check(queue_status="pending").allowed


def test_failed_job_rejected():
    assert not check(queue_status="failed").allowed


def test_missing_claim_rejected():
    assert not check(claim_token=None).allowed


def test_stale_claim_rejected():
    assert not check(
        expected_claim_token="different-worker"
    ).allowed


def test_expired_lease_rejected():
    assert not check(lease_expires_at=NOW).allowed


def test_missing_lease_rejected():
    assert not check(lease_expires_at=None).allowed


def test_rotated_token_rejected():
    assert not check(
        queue_token_hash="a" * 64
    ).allowed


def test_consumed_token_rejected():
    assert not check(
        token_consumed_at=NOW
    ).allowed


def test_expired_active_token_rejected():
    assert not check(
        token_expires_at=NOW
    ).allowed


def test_expired_queue_rejected():
    assert not check(
        queue_expires_at=NOW
    ).allowed


def test_expiry_mismatch_rejected():
    assert not check(
        queue_expires_at=NOW + timedelta(minutes=29)
    ).allowed


def test_valid_encrypted_token_decrypts():
    challenge = issue_challenge(NOW)
    key = Fernet.generate_key().decode("ascii")

    encrypted = encrypt_token(
        challenge.raw_token,
        key,
    )

    recovered = decrypt_eligible_token(
        encrypted_token=encrypted,
        encryption_key=key,
        expected_token_hash=challenge.token_hash,
    )

    assert recovered == challenge.raw_token


def test_wrong_token_hash_rejected_after_decryption():
    challenge = issue_challenge(NOW)
    key = Fernet.generate_key().decode("ascii")

    encrypted = encrypt_token(
        challenge.raw_token,
        key,
    )

    with pytest.raises(ValueError):
        decrypt_eligible_token(
            encrypted_token=encrypted,
            encryption_key=key,
            expected_token_hash="a" * 64,
        )


def test_wrong_encryption_key_rejected():
    challenge = issue_challenge(NOW)
    key = Fernet.generate_key().decode("ascii")
    other_key = Fernet.generate_key().decode("ascii")

    encrypted = encrypt_token(
        challenge.raw_token,
        key,
    )

    with pytest.raises(ValueError):
        decrypt_eligible_token(
            encrypted_token=encrypted,
            encryption_key=other_key,
            expected_token_hash=challenge.token_hash,
        )
