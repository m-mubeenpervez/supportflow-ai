from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)

from sqlalchemy import (
    DateTime as _CustomerDateTime,
    func as _customer_func,
)

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Tombstone keeps support FK relationships intact while removing account access.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


    session_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )


    created_at: Mapped[datetime | None] = mapped_column(
        _CustomerDateTime(timezone=True),
        nullable=True,
        server_default=_customer_func.now(),
    )

class Order(Base):
    __tablename__='orders'
    id: Mapped[str]=mapped_column(String(32),primary_key=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey('customers.id'))
    item: Mapped[str]=mapped_column(String(200))
    status: Mapped[str]=mapped_column(String(32))
    total: Mapped[int]=mapped_column(Integer)
    placed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Ticket(Base):
    __tablename__='tickets'
    id: Mapped[int]=mapped_column(primary_key=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey('customers.id'))
    order_id: Mapped[str|None]=mapped_column(String(32),nullable=True)
    intent: Mapped[str]=mapped_column(String(40),default='general')
    status: Mapped[str]=mapped_column(String(32),default='open')
    priority: Mapped[str]=mapped_column(String(20),default='normal')
    summary: Mapped[str]=mapped_column(Text,default='')
    response: Mapped[str]=mapped_column(Text,default='')
    approved: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    customer_hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class Message(Base):
    __tablename__='messages'
    id: Mapped[int]=mapped_column(primary_key=True)
    ticket_id: Mapped[int]=mapped_column(ForeignKey('tickets.id'))
    role: Mapped[str]=mapped_column(String(16))
    content: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Audit(Base):
    __tablename__='audit'
    id: Mapped[int]=mapped_column(primary_key=True)
    ticket_id: Mapped[int]=mapped_column(ForeignKey('tickets.id'))
    action: Mapped[str]=mapped_column(String(60))
    details: Mapped[str]=mapped_column(Text,default='')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)


# ==========================================================
# SUPPORTFLOW AI - PERSISTENT NOTIFICATIONS
# ==========================================================

class Notification(Base):
    """In-app notification for an admin or customer."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    event_key: Mapped[str] = mapped_column(
        String(160),
        unique=True,
        nullable=False,
    )

    recipient_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
    )

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )


class EmailOutbox(Base):
    """Persistent record for retryable email delivery."""

    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)

    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id"),
        unique=True,
        nullable=False,
    )

    recipient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )

    # Email worker ownership and crash recovery
    claim_token: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )


# ==========================================================
# SUPPORTFLOW AI - CUSTOMER EMAIL VERIFICATION TOKENS
# ==========================================================

class EmailVerificationToken(Base):
    """One active/recent verification challenge per customer.

    Only a SHA-256 digest is stored; never store raw tokens.
    """

    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        unique=True,
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )

    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ==========================================================
# SUPPORTFLOW AI - SECURE VERIFICATION EMAIL OUTBOX
# ==========================================================

class VerificationEmailOutbox(Base):
    """Retryable encrypted email-verification delivery record.

    Never store a raw verification token or plaintext
    verification link in this table.
    """

    __tablename__ = "verification_email_outbox"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        unique=True,
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    encrypted_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )

    claim_token: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )

from sqlalchemy import func


class AdminUser(Base):
    """Separate administrative identity."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="admin",
        server_default="admin",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    session_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CustomerActionEmailOutbox(Base):
    """Independent transactional queue for customer account lifecycle notices."""

    __tablename__ = "customer_action_email_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
