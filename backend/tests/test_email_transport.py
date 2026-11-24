"""Mocked tests for the SMTP transport."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import email_transport


def smtp_settings(**overrides):
    values = {
        "email_delivery_enabled": True,
        "email_delivery_mode": "test",
        "email_test_allowed_recipients": "allowed-one@example.com,allowed-two@example.com",
        "email_smtp_starttls": True,
        "email_smtp_host": "smtp.example.test",
        "email_smtp_port": 587,
        "email_smtp_timeout_seconds": 5,
        "email_smtp_username": "test-user",
        "email_smtp_password": "test-password",
        "email_from_address": "support@example.test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_email_disabled_rejects_without_network():
    with patch.object(
        email_transport,
        "settings",
        smtp_settings(email_delivery_enabled=False),
    ), patch.object(
        email_transport.smtplib,
        "SMTP",
    ) as smtp:
        with pytest.raises(RuntimeError, match="disabled"):
            asyncio.run(
                email_transport.send_email(
                    "allowed-one@example.com",
                    "Decision",
                    "Your request was reviewed.",
                )
            )

        smtp.assert_not_called()


def test_smtp_success_uses_starttls_and_login():
    smtp_instance = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = smtp_instance

    with patch.object(
        email_transport,
        "settings",
        smtp_settings(),
    ), patch.object(
        email_transport.smtplib,
        "SMTP",
        return_value=context,
    ) as smtp:
        email_transport._send_smtp(
            "allowed-one@example.com",
            "Request approved",
            "Your request was approved.",
        )

        smtp.assert_called_once()
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with(
            "test-user",
            "test-password",
        )
        smtp_instance.send_message.assert_called_once()

        message = smtp_instance.send_message.call_args.args[0]
        assert message["To"] == "allowed-one@example.com"
        assert message["Subject"] == "Request approved"


def test_starttls_cannot_be_disabled():
    with patch.object(
        email_transport,
        "settings",
        smtp_settings(email_smtp_starttls=False),
    ), patch.object(
        email_transport.smtplib,
        "SMTP",
    ) as smtp:
        with pytest.raises(RuntimeError, match="STARTTLS"):
            email_transport._send_smtp(
                "allowed-one@example.com",
                "Update",
                "Message",
            )

        smtp.assert_not_called()


@pytest.mark.parametrize(
    "address",
    [
        "",
        "invalid-email",
        "person@",
        "@example.test",
        "person@example.test" + chr(13) + chr(10) + "Bcc:other@example.test",
    ],
)
def test_invalid_recipients_rejected(address):
    with patch.object(
        email_transport,
        "settings",
        smtp_settings(),
    ), patch.object(
        email_transport.smtplib,
        "SMTP",
    ) as smtp:
        with pytest.raises(ValueError):
            email_transport._send_smtp(
                address,
                "Update",
                "Message",
            )

        smtp.assert_not_called()


def test_invalid_subject_rejected():
    with patch.object(
        email_transport,
        "settings",
        smtp_settings(),
    ), patch.object(
        email_transport.smtplib,
        "SMTP",
    ) as smtp:
        with pytest.raises(ValueError):
            email_transport._send_smtp(
                "allowed-one@example.com",
                "Update" + chr(10) + "Bcc: attacker@example.test",
                "Message",
            )

        smtp.assert_not_called()


def test_smtp_failure_propagates():
    smtp_instance = MagicMock()
    smtp_instance.send_message.side_effect = (
        email_transport.smtplib.SMTPException(
            "Simulated SMTP failure"
        )
    )
    context = MagicMock()
    context.__enter__.return_value = smtp_instance

    with patch.object(
        email_transport,
        "settings",
        smtp_settings(),
    ), patch.object(
        email_transport.smtplib,
        "SMTP",
        return_value=context,
    ):
        with pytest.raises(
            email_transport.smtplib.SMTPException
        ):
            email_transport._send_smtp(
                "allowed-one@example.com",
                "Update",
                "Message",
            )


def test_live_allowlist_rejects_unauthorized_recipient_without_smtp():
    with patch.object(email_transport, "settings", smtp_settings()), patch.object(
        email_transport.smtplib, "SMTP"
    ) as smtp:
        with pytest.raises(ValueError, match="not authorized"):
            email_transport._send_smtp(
                "unrelated@example.com", "Update", "Message"
            )
        smtp.assert_not_called()
