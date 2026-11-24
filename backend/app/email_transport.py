"""Secure SMTP transport for queued SupportFlow AI emails.

This module does not poll the database or start a worker.
"""

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

from .config import settings


def configured_test_recipients() -> frozenset[str]:
    """Return the validated private test-mode recipient set."""
    raw = getattr(settings, "email_test_allowed_recipients", "")
    return frozenset(
        item.strip().casefold()
        for item in raw.split(",")
        if item.strip()
    )


def validate_email_address(address: str) -> str:
    """Validate a simple mailbox address without display names."""

    if not isinstance(address, str):
        raise ValueError("Invalid email address")

    value = address.strip()

    if (
        not value
        or len(value) > 254
        or any(char in value for char in (chr(13), chr(10), chr(9), " "))
        or value.count("@") != 1
        or parseaddr(value)[1] != value
    ):
        raise ValueError("Invalid email address")

    local, domain = value.rsplit("@", 1)

    if (
        not local
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        raise ValueError("Invalid email address")

    return value


def validate_delivery_recipient(address: str) -> str:
    """Validate and enforce the explicit live-test recipient allowlist."""

    value = validate_email_address(address)
    mode = getattr(settings, "email_delivery_mode", "")
    if mode not in {"test", "production"}:
        raise ValueError("Invalid email delivery mode")
    if mode == "test" and value.casefold() not in configured_test_recipients():
        raise ValueError("Recipient is not authorized for live SMTP testing")
    return value


def _send_smtp(
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Send one message using verified SMTP configuration."""

    if not settings.email_delivery_enabled:
        raise RuntimeError("Email delivery is disabled")

    if not settings.email_smtp_starttls:
        raise RuntimeError("SMTP STARTTLS is required")

    if not settings.email_smtp_host:
        raise RuntimeError("SMTP host is not configured")

    sender = validate_email_address(
        settings.email_from_address
    )
    recipient = validate_delivery_recipient(recipient)

    if (
        not isinstance(subject, str)
        or not subject.strip()
        or chr(13) in subject
        or chr(10) in subject
    ):
        raise ValueError("Invalid email subject")

    if not isinstance(body, str) or not body.strip():
        raise ValueError("Invalid email body")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(
        settings.email_smtp_host,
        settings.email_smtp_port,
        timeout=settings.email_smtp_timeout_seconds,
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()

        if settings.email_smtp_username:
            if not settings.email_smtp_password:
                raise RuntimeError(
                    "SMTP password is not configured"
                )

            smtp.login(
                settings.email_smtp_username,
                settings.email_smtp_password,
            )

        smtp.send_message(message)


async def send_email(
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Run blocking SMTP work outside the async event loop."""

    if not settings.email_delivery_enabled:
        raise RuntimeError("Email delivery is disabled")

    await asyncio.to_thread(
        _send_smtp,
        recipient,
        subject,
        body,
    )
