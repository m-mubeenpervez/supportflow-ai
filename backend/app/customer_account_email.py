"""Transactional email notices for administrator actions on customer accounts.

Account notices are intentionally independent of support-ticket notifications:
customer deletion can occur without a ticket. No SMTP I/O is performed here.
"""

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .email_transport import validate_email_address
from .models import CustomerActionEmailOutbox


def eligible_address(customer):
    """Notify only addresses verified before account deactivation/removal."""
    if customer.email_verified_at is None:
        return None
    try:
        return validate_email_address(customer.email)
    except ValueError:
        return None


async def queue_customer_account_notice(
    db: AsyncSession,
    *,
    customer_id: int,
    email: str | None,
    kind: str,
    event_key: str,
):
    """Stage mail atomically with the account change; delivery remains opt-in."""
    if kind not in {"deactivated", "activated", "removed"}:
        raise ValueError("Unsupported account notice")
    if not settings.email_delivery_enabled or not email:
        return None
    recipient = validate_email_address(email)

    templates = {
        "deactivated": (
            "Your SupportFlow account has been deactivated",
            "Your SupportFlow AI account was deactivated by the support team. "
            "You cannot sign in while it is deactivated. If you believe this "
            "is an error, contact support through your usual support channel.",
        ),
        "activated": (
            "Your SupportFlow account has been reactivated",
            "Your SupportFlow AI account was reactivated by the support team. "
            "You can now sign in again. If you did not expect this change, "
            "please contact support.",
        ),
        "removed": (
            "Your SupportFlow account has been removed",
            "Your SupportFlow AI account has been removed at the support team's "
            "direction. You can no longer sign in with the removed account. "
            "Support records may be retained for recordkeeping. "
            "Contact support if you believe this was a mistake.",
        ),
    }
    subject, body = templates[kind]
    notice = CustomerActionEmailOutbox(
        customer_id=customer_id,
        event_key=event_key,
        kind=kind,
        recipient_email=recipient,
        subject=subject,
        body=body,
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(notice)
    await db.flush()
    return notice


async def cancel_prior_account_notices(db: AsyncSession, customer_id: int):
    """Prevent old queued account notices from using a removed mailbox."""
    await db.execute(
        update(CustomerActionEmailOutbox)
        .where(
            CustomerActionEmailOutbox.customer_id == customer_id,
            CustomerActionEmailOutbox.status.in_(["pending", "retry", "processing"]),
        )
        .values(
            status="cancelled",
            recipient_email=f"deleted-customer-{customer_id}@deleted.invalid",
            claim_token=None,
            lease_expires_at=None,
            body="Account notice cancelled after removal.",
        )
    )
