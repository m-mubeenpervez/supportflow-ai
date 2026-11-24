"""Tests for safe notification recipient selection."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import email_recipients


def customer(email, verified_at=None):
    return SimpleNamespace(
        email=email,
        email_verified_at=verified_at,
    )


def enable(monkeypatch, enabled=True):
    monkeypatch.setattr(
        email_recipients.settings,
        "email_delivery_enabled",
        enabled,
    )
    monkeypatch.setattr(
        email_recipients.settings,
        "email_delivery_mode",
        "test",
    )
    monkeypatch.setattr(
        email_recipients.settings,
        "email_test_allowed_recipients",
        "allowed-one@example.com,allowed-two@example.com",
    )


def test_admin_valid_configured_address(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(
        email_recipients.settings,
        "admin_notification_email",
        "allowed-two@example.com",
    )

    assert (
        email_recipients.admin_notification_recipient()
        == "allowed-two@example.com"
    )


def test_admin_missing_address(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(
        email_recipients.settings,
        "admin_notification_email",
        "",
    )

    assert email_recipients.admin_notification_recipient() is None


def test_admin_invalid_address(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(
        email_recipients.settings,
        "admin_notification_email",
        "invalid-address",
    )

    assert email_recipients.admin_notification_recipient() is None


def test_disabled_admin_email(monkeypatch):
    enable(monkeypatch, False)

    assert email_recipients.admin_notification_recipient() is None


def test_verified_customer_eligible(monkeypatch):
    enable(monkeypatch)

    user = customer(
        "allowed-one@example.com",
        datetime.now(timezone.utc),
    )

    assert (
        email_recipients.customer_notification_recipient(user)
        == "allowed-one@example.com"
    )


def test_unverified_customer_not_eligible(monkeypatch):
    enable(monkeypatch)

    user = customer("customer@example.test")

    assert (
        email_recipients.customer_notification_recipient(user)
        is None
    )


def test_existing_customer_model_fails_closed(monkeypatch):
    enable(monkeypatch)

    # Models without verification fields cannot qualify.
    user = SimpleNamespace(
        email="customer@example.test",
    )

    assert (
        email_recipients.customer_notification_recipient(user)
        is None
    )


def test_naive_verification_timestamp_rejected(monkeypatch):
    enable(monkeypatch)

    user = customer(
        "customer@example.test",
        datetime(2026, 11, 17),
    )

    assert (
        email_recipients.customer_notification_recipient(user)
        is None
    )


@pytest.mark.parametrize(
    "address",
    [
        "",
        "invalid",
        "customer@",
        "customer@example.test" + chr(10) + "Bcc:bad@example.test",
    ],
)
def test_invalid_customer_addresses_rejected(
    monkeypatch,
    address,
):
    enable(monkeypatch)

    user = customer(
        address,
        datetime.now(timezone.utc),
    )

    assert (
        email_recipients.customer_notification_recipient(user)
        is None
    )


def test_disabled_customer_email(monkeypatch):
    enable(monkeypatch, False)

    user = customer(
        "customer@example.test",
        datetime.now(timezone.utc),
    )

    assert (
        email_recipients.customer_notification_recipient(user)
        is None
    )


def test_missing_customer_rejected(monkeypatch):
    enable(monkeypatch)

    assert (
        email_recipients.customer_notification_recipient(None)
        is None
    )
