"""Process one verification email with explicit delivery controls.

No background loop. No automatic SMTP startup.
A mock sender may be injected for isolated integration tests.
"""

from urllib.parse import urlencode, urlsplit, urlunsplit

from cryptography.fernet import Fernet
from sqlalchemy import select

from .config import settings
from .db import Session
from .email_transport import send_email, validate_email_address
from .models import Customer
from .verification_delivery_policy import decrypt_eligible_token
from .verification_delivery_state import (
    mark_verification_failed,
    mark_verification_sent,
    retire_verification_claim,
)
from .verification_email_worker import claim_verification_email
from .verification_pre_send import validate_claim_before_send


def build_verification_url(base_url: str, raw_token: str) -> str:
    """Create a verification link without accepting unsafe origins."""

    if not isinstance(base_url, str):
        raise ValueError("Invalid verification URL")

    parsed = urlsplit(base_url)

    local = (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    )

    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"https", "http"}
        or (parsed.scheme != "https" and not local)
        or any(char.isspace() for char in base_url)
    ):
        raise ValueError("Unsafe verification URL")

    # Validate token before including it in the URL.
    from .email_verification import hash_token
    hash_token(raw_token)

    path = parsed.path.rstrip("/") or "/verify-email"

    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        path,
        urlencode({"token": raw_token}),
        "",
    ))


async def process_one_verification_email(
    session_factory=Session,
    *,
    sender=None,
    encryption_key: str,
    verification_base_url: str,
    allow_mock_delivery: bool = False,
) -> str:
    """Process one job, returning a safe non-sensitive status.

    The mock override requires an injected sender and must
    never be used to invoke real SMTP while delivery is disabled.
    """

    if not settings.email_delivery_enabled:
        if not allow_mock_delivery:
            return "disabled"

        if sender is None or sender is send_email:
            raise RuntimeError(
                "Disabled delivery requires an injected mock sender"
            )

    if not isinstance(encryption_key, str):
        raise ValueError("Invalid encryption key")

    # Fail before claiming a job if configuration is invalid.
    try:
        Fernet(encryption_key.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid encryption key") from exc

    # Validate the URL without creating a real verification token.
    test_token = "A" * 43
    build_verification_url(
        verification_base_url, test_token
    )

    job = await claim_verification_email(
        session_factory=session_factory,
        allow_mock_delivery=allow_mock_delivery,
    )

    if job is None:
        return "empty"

    eligibility = await validate_claim_before_send(
        job, session_factory
    )

    if not eligibility.allowed:
        retired = await retire_verification_claim(
            job, session_factory
        )
        return "ineligible" if retired else "ownership_lost"

    try:
        raw_token = decrypt_eligible_token(
            encrypted_token=job.encrypted_token,
            encryption_key=encryption_key,
            expected_token_hash=job.token_hash,
        )

        link = build_verification_url(
            verification_base_url, raw_token
        )

        # Never take the recipient from an untrusted API input.
        async with session_factory() as db:
            recipient = await db.scalar(
                select(Customer.email).where(
                    Customer.id == job.customer_id,
                    Customer.email_verified_at.is_(None),
                )
            )

        if recipient is None:
            retired = await retire_verification_claim(
                job, session_factory
            )
            return "ineligible" if retired else "ownership_lost"

        recipient = validate_email_address(recipient)

        # Check again after resolving the recipient.
        eligibility = await validate_claim_before_send(
            job, session_factory
        )

        if not eligibility.allowed:
            retired = await retire_verification_claim(
                job, session_factory
            )
            return "ineligible" if retired else "ownership_lost"

        body = (
            "Verify your SupportFlow AI email address:\n\n"
            + link
            + "\n\nThis link expires in 30 minutes. "
            + "If you did not create this account, "
            + "ignore this email."
        )

        delivery_sender = sender or send_email

        await delivery_sender(
            recipient,
            "Verify your SupportFlow AI email",
            body,
        )

    except Exception as exc:
        # Do not log exception details or include token in result.
        return await mark_verification_failed(
            job, exc, session_factory
        )

    updated = await mark_verification_sent(
        job, session_factory
    )

    return "sent" if updated else "ownership_lost"
