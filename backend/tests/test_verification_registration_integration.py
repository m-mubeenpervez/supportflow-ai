"""PostgreSQL integration tests for atomic registration.

Uses isolated worker_database schemas, not supportflow_db.
No SMTP or external API calls.
"""

import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import verify_password
from app.email_verification import hash_token
from app.models import (
    Customer,
    EmailVerificationToken,
    VerificationEmailOutbox,
)
from app.verification_email_crypto import decrypt_token
from app.verification_registration import (
    register_customer_with_verification,
)

from test_email_worker_integration import worker_database


def new_email():
    return f"registration-{uuid.uuid4().hex}@example.test"


def new_key():
    return Fernet.generate_key().decode("ascii")


async def count_rows(factory, model):
    async with factory() as db:
        return await db.scalar(
            select(func.count()).select_from(model)
        )


@pytest.mark.asyncio
async def test_registration_creates_customer_token_and_queue(
    worker_database,
):
    email = new_email()
    key = new_key()

    async with worker_database() as db:
        async with db.begin():
            result = await register_customer_with_verification(
                db,
                name="Registration Test",
                email=email.upper(),
                password="TestPassword123!",
                encryption_key=key,
            )

    assert result["email"] == email
    assert set(result) == {"id", "name", "email"}

    async with worker_database() as db:
        customer = await db.get(Customer, result["id"])

        token = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.customer_id
                == result["id"]
            )
        )

        queue = await db.scalar(
            select(VerificationEmailOutbox).where(
                VerificationEmailOutbox.customer_id
                == result["id"]
            )
        )

        assert customer is not None
        assert customer.email_verified_at is None
        assert customer.password_hash != "TestPassword123!"
        assert verify_password(
            "TestPassword123!",
            customer.password_hash,
        )

        assert token is not None
        assert queue is not None
        assert queue.status == "pending"
        assert queue.attempts == 0
        assert queue.token_hash == token.token_hash

        raw_token = decrypt_token(
            queue.encrypted_token,
            key,
        )

        assert hash_token(raw_token) == token.token_hash
        assert raw_token not in str(result)


@pytest.mark.asyncio
async def test_invalid_encryption_key_rolls_back_customer(
    worker_database,
):
    before = await count_rows(worker_database, Customer)

    with pytest.raises(ValueError):
        async with worker_database() as db:
            async with db.begin():
                await register_customer_with_verification(
                    db,
                    name="Rollback Test",
                    email=new_email(),
                    password="TestPassword123!",
                    encryption_key="invalid-key",
                )

    assert await count_rows(
        worker_database, Customer
    ) == before

    assert await count_rows(
        worker_database, VerificationEmailOutbox
    ) == 0


@pytest.mark.asyncio
async def test_duplicate_email_does_not_create_second_queue(
    worker_database,
):
    email = new_email()
    key = new_key()

    async with worker_database() as db:
        async with db.begin():
            await register_customer_with_verification(
                db,
                name="First Customer",
                email=email,
                password="TestPassword123!",
                encryption_key=key,
            )

    with pytest.raises(IntegrityError):
        async with worker_database() as db:
            async with db.begin():
                await register_customer_with_verification(
                    db,
                    name="Duplicate Customer",
                    email=email,
                    password="TestPassword456!",
                    encryption_key=key,
                )

    assert await count_rows(
        worker_database, Customer
    ) == 1

    assert await count_rows(
        worker_database, EmailVerificationToken
    ) == 1

    assert await count_rows(
        worker_database, VerificationEmailOutbox
    ) == 1


@pytest.mark.asyncio
async def test_queue_exception_rolls_back_registration(
    worker_database,
    monkeypatch,
):
    import app.verification_registration as module

    async def broken_queue(*args, **kwargs):
        raise RuntimeError("Simulated queue failure")

    monkeypatch.setattr(
        module,
        "queue_verification_email",
        broken_queue,
    )

    with pytest.raises(RuntimeError, match="Simulated"):
        async with worker_database() as db:
            async with db.begin():
                await register_customer_with_verification(
                    db,
                    name="Queue Failure Test",
                    email=new_email(),
                    password="TestPassword123!",
                    encryption_key=new_key(),
                )

    assert await count_rows(
        worker_database, Customer
    ) == 0

    assert await count_rows(
        worker_database, EmailVerificationToken
    ) == 0

    assert await count_rows(
        worker_database, VerificationEmailOutbox
    ) == 0


@pytest.mark.asyncio
async def test_requires_caller_owned_transaction(
    worker_database,
):
    async with worker_database() as db:
        with pytest.raises(
            RuntimeError,
            match="active transaction",
        ):
            await register_customer_with_verification(
                db,
                name="No Transaction",
                email=new_email(),
                password="TestPassword123!",
                encryption_key=new_key(),
            )

    assert await count_rows(
        worker_database, Customer
    ) == 0
