"""Option A customer removal: anonymize identity, keep FK-linked support history.

This module does NOT commit, send mail, or delete ticket/order/message history.
Caller must hold the Customer row lock and own an atomic transaction.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case, delete, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Customer, Ticket, EmailVerificationToken, VerificationEmailOutbox,
    Notification, EmailOutbox,
)


def removed_email(customer_id: int) -> str:
    """Reserved mailbox; never use an actual deliverable email address."""
    return f"deleted-customer-{customer_id}@deleted.invalid"


async def anonymize_customer_account(db: AsyncSession, customer: Customer) -> dict:
    """Anonymize a deactivated account in-place, preserving FK references.

    The caller logs the actor/reason in AdminActivity and commits atomically.
    """
    if customer.deleted_at is not None:
        raise HTTPException(404, "Customer account already removed")
    if customer.deactivated_at is None:
        raise HTTPException(409, "Deactivate customer before removal")

    pending = await db.scalar(select(func.count(Ticket.id)).where(
        Ticket.customer_id == customer.id, Ticket.status == "pending_approval"
    ))
    if pending:
        raise HTTPException(409, "Resolve pending human approvals before account removal")

    # No new email-verification token can authenticate the removed account.
    # Cancel queued verification and delete encrypted verification material.
    await db.execute(delete(VerificationEmailOutbox).where(
        VerificationEmailOutbox.customer_id == customer.id
    ))
    await db.execute(delete(EmailVerificationToken).where(
        EmailVerificationToken.customer_id == customer.id
    ))

    # Preserve notification/outbox row IDs for auditability, but remove mailbox
    # and queued customer email contents. Must stop email workers before applying.
    notification_ids = select(Notification.id).where(
        Notification.customer_id == customer.id,
        Notification.recipient_type == "customer",
    )
    await db.execute(update(EmailOutbox).where(
        EmailOutbox.notification_id.in_(notification_ids)
    ).values(
        recipient_email=removed_email(customer.id),
        subject="Customer account removed",
        body="Customer account removed. Delivery disabled.",
        status=case(
            (EmailOutbox.status.in_(["pending", "retry", "processing"]), "cancelled"),
            else_=EmailOutbox.status,
        ),
        claim_token=None,
        lease_expires_at=None,
        last_error=None,
    ))

    customer.name = f"Deleted customer #{customer.id}"
    customer.email = removed_email(customer.id)
    customer.password_hash = None
    customer.email_verified_at = None
    customer.session_version += 1
    customer.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "deleted": True,
        "customer_id": customer.id,
        "method": "anonymized_tombstone",
        "history_preserved": True,
    }
