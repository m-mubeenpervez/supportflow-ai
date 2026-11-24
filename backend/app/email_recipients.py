"""Safe recipient selection for notification emails.

No database access, network calls, or email delivery.
Unverified customers are never selected for email.
"""

from datetime import datetime

from .config import settings
from .email_transport import validate_delivery_recipient


def _safe_email(value):
    """Return a valid mailbox or None, without raising."""

    try:
        return validate_delivery_recipient(value)
    except ValueError:
        return None


def admin_notification_recipient():
    """Select an explicitly configured admin mailbox."""

    if not settings.email_delivery_enabled:
        return None

    return _safe_email(
        settings.admin_notification_email
    )


def dedupe_recipients(values):
    """Return valid, unique mailboxes while preserving order."""
    result = []
    seen = set()
    for value in values:
        email = _safe_email(value)
        if email is not None and email.casefold() not in seen:
            seen.add(email.casefold())
            result.append(email)
    return result


def customer_notification_recipient(customer):
    """Select only an email-verified ticket owner's address."""

    if not settings.email_delivery_enabled:
        return None

    if customer is None:
        return None

    if getattr(customer, "deleted_at", None) is not None:
        return None

    verified_at = getattr(
        customer,
        "email_verified_at",
        None,
    )

    if not isinstance(verified_at, datetime):
        return None

    if verified_at.tzinfo is None:
        return None

    return _safe_email(
        getattr(customer, "email", None)
    )
