"""Revalidate verification email claims immediately before delivery.

No SMTP calls, decryption, commits, or logging of secrets.
"""

import secrets

from sqlalchemy import select

from .db import Session
from .models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from .verification_delivery_policy import (
    DeliveryEligibility,
    check_delivery_eligibility,
)


async def validate_claim_before_send(
    job,
    session_factory=Session,
) -> DeliveryEligibility:
    """Recheck the current DB state and worker ownership.

    Locks are acquired in customer -> token -> outbox order.
    Locks are released when this validation transaction exits.

    The caller must not assume that this prevents changes
    during a later SMTP request.
    """

    async with session_factory() as db:
        async with db.begin():
            customer = await db.scalar(
                select(Customer)
                .where(Customer.id == job.customer_id)
                .with_for_update()
            )

            if customer is None:
                return DeliveryEligibility(
                    False, "customer_missing"
                )

            token = await db.scalar(
                select(EmailVerificationToken)
                .where(
                    EmailVerificationToken.customer_id
                    == job.customer_id
                )
                .with_for_update()
            )

            if token is None:
                return DeliveryEligibility(
                    False, "token_missing"
                )

            outbox = await db.scalar(
                select(VerificationEmailOutbox)
                .where(
                    VerificationEmailOutbox.id == job.id,
                    VerificationEmailOutbox.customer_id
                    == job.customer_id,
                )
                .with_for_update()
            )

            if outbox is None:
                return DeliveryEligibility(
                    False, "outbox_missing"
                )

            # Do not process a replaced queue payload.
            if not secrets.compare_digest(
                outbox.token_hash,
                job.token_hash,
            ):
                return DeliveryEligibility(
                    False, "queue_replaced"
                )

            if not secrets.compare_digest(
                outbox.encrypted_token,
                job.encrypted_token,
            ):
                return DeliveryEligibility(
                    False, "payload_replaced"
                )

            if outbox.expires_at != job.expires_at:
                return DeliveryEligibility(
                    False, "job_expiry_changed"
                )

            return check_delivery_eligibility(
                customer_verified_at=customer.email_verified_at,
                active_token_hash=token.token_hash,
                token_expires_at=token.expires_at,
                token_consumed_at=token.consumed_at,
                queue_token_hash=outbox.token_hash,
                queue_expires_at=outbox.expires_at,
                queue_status=outbox.status,
                claim_token=outbox.claim_token,
                expected_claim_token=job.claim_token,
                lease_expires_at=outbox.lease_expires_at,
            )
