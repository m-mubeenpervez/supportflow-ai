"""Persistent notification creation for SupportFlow AI.

Call these helpers inside the caller's existing database transaction.
They never commit, send emails, or execute financial operations.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .email_recipients import dedupe_recipients
from .models import AdminUser, EmailOutbox, Notification, Ticket


async def create_notification(
    db: AsyncSession,
    *,
    event_key: str,
    recipient_type: str,
    ticket_id: int,
    event_type: str,
    title: str,
    body: str,
    customer_id: int | None = None,
    recipient_email: str | None = None,
) -> Notification:
    """Stage one notification and optional email in the same transaction."""

    if recipient_type not in {"admin", "customer"}:
        raise ValueError("Invalid notification recipient type")

    if recipient_type == "customer" and customer_id is None:
        raise ValueError("Customer notifications require customer_id")

    if recipient_type == "admin" and customer_id is not None:
        raise ValueError("Admin notifications cannot have customer_id")

    if not event_key or len(event_key) > 160:
        raise ValueError("Invalid notification event key")

    if not title or not body:
        raise ValueError("Notification title and body are required")

    notification = Notification(
        event_key=event_key,
        recipient_type=recipient_type,
        customer_id=customer_id,
        ticket_id=ticket_id,
        event_type=event_type,
        title=title,
        body=body,
    )

    db.add(notification)

    if recipient_email:
        email = recipient_email.strip()

        if not email or len(email) > 255 or "@" not in email:
            raise ValueError("Invalid notification email address")

        # Flush to obtain the notification ID.
        # Transaction ownership remains with the caller.
        await db.flush()

        db.add(
            EmailOutbox(
                notification_id=notification.id,
                recipient_email=email,
                subject=title,
                body=body,
            )
        )

    return notification


async def notify_admin_approval_requested(
    db: AsyncSession,
    *,
    ticket: Ticket,
    admin_email: str | None = None,
    admin_emails: list[str] | None = None,
) -> Notification:
    """Notify admins that an approval decision is required."""

    if ticket.id is None or ticket.status != "pending_approval":
        raise ValueError("Ticket must be pending human approval")

    title = f"Ticket #{ticket.id} requires human approval"
    body = (
        f"Support ticket #{ticket.id} is awaiting review. "
        "Open the admin dashboard to inspect the conversation "
        "and record a decision."
    )
    # `admin_emails` is resolved from authorized admin records and already
    # mode-filtered. Keep the legacy explicit override for isolated callers;
    # the SMTP transport remains the final recipient enforcement boundary.
    recipients = []
    seen = set()
    for value in (admin_emails or []) + ([admin_email] if admin_email else []):
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            if normalized.casefold() not in seen:
                seen.add(normalized.casefold())
                recipients.append(normalized)
    if not recipients:
        recipients = [None]
    first = None
    for index, recipient in enumerate(recipients):
        notification = await create_notification(
            db,
            event_key=f"ticket:{ticket.id}:admin:approval_requested:{index}",
            recipient_type="admin",
            ticket_id=ticket.id,
            event_type="approval_requested",
            title=title,
            body=body,
            recipient_email=recipient,
        )
        first = first or notification
    return first


async def active_admin_notification_recipients(db: AsyncSession) -> list[str]:
    """Resolve active admin mailboxes, deduplicated and mode-filtered."""
    from .config import settings
    from .email_recipients import dedupe_recipients
    if not settings.email_delivery_enabled:
        return []
    rows = await db.scalars(
        select(AdminUser.email).where(
            AdminUser.is_active.is_(True),
            AdminUser.role.in_({"admin", "super_admin"}),
        ).order_by(AdminUser.id)
    )
    return dedupe_recipients(rows.all())


async def notify_customer_decision(
    db: AsyncSession,
    *,
    ticket: Ticket,
    customer_email: str | None = None,
) -> Notification:
    """Notify the ticket owner after an admin decision is recorded."""

    if ticket.id is None or ticket.status not in {"approved", "rejected"}:
        raise ValueError("Ticket must have a final human decision")

    approved = ticket.status == "approved"

    if approved:
        title = f"Support ticket #{ticket.id} approved"
        body = (
            f"Your support request #{ticket.id} was approved "
            "by the support team. This approval does not mean "
            "a refund has been paid or an order has been cancelled."
        )
    else:
        title = f"Support ticket #{ticket.id} not approved"
        body = (
            f"Your support request #{ticket.id} was reviewed "
            "and was not approved. Contact support if you "
            "need further assistance."
        )

    return await create_notification(
        db,
        event_key=f"ticket:{ticket.id}:customer:{ticket.status}",
        recipient_type="customer",
        customer_id=ticket.customer_id,
        ticket_id=ticket.id,
        event_type=f"request_{ticket.status}",
        title=title,
        body=body,
        recipient_email=customer_email,
    )
