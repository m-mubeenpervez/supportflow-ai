"""Atomic customer registration with verification email queue.

Caller owns the database transaction.
Never return the raw verification token.
No SMTP calls or automatic commits.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from .auth import hash_password
from .models import Customer
from .verification_email_queue import queue_verification_email


async def register_customer_with_verification(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
    encryption_key: str,
) -> dict:
    """Stage customer and email challenge in one transaction.

    Caller must use ``async with db.begin()``.
    Any failure must cause the caller to roll back.
    """

    if not db.in_transaction():
        raise RuntimeError(
            "Registration requires an active transaction"
        )

    normalized_email = email.strip().lower()

    if not normalized_email:
        raise ValueError("Customer email is required")

    customer = Customer(
        name=name,
        email=normalized_email,
        password_hash=hash_password(password),
    )

    db.add(customer)
    await db.flush()

    await queue_verification_email(
        db,
        customer_id=customer.id,
        encryption_key=encryption_key,
    )

    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
    }
