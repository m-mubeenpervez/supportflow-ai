"""Isolated tests for local administrator provisioning."""

import pytest

from app.admin_provisioning import (
    AdminProvisioningError,
    normalize_admin_email,
    validate_admin_password,
    prepare_admin_credentials,
)
from app.auth import verify_password


def test_admin_email_normalization():
    assert normalize_admin_email(
        "  Admin@Example.com "
    ) == "admin@example.com"


@pytest.mark.parametrize(
    "email",
    [
        "",
        "invalid",
        "admin@",
        None,
        123,
    ],
)
def test_invalid_admin_email_rejected(email):
    with pytest.raises(AdminProvisioningError):
        normalize_admin_email(email)


def test_valid_admin_password():
    validate_admin_password(
        "Secure-Admin-Passphrase-2026"
    )


@pytest.mark.parametrize(
    "password",
    [
        "",
        "short",
        "A" * 73,
        "validpassword\n",
        None,
        123,
    ],
)
def test_invalid_admin_password_rejected(password):
    with pytest.raises(AdminProvisioningError):
        validate_admin_password(password)


def test_provisioning_returns_password_hash():
    password = "Secure-Admin-Passphrase-2026"

    email, password_hash = prepare_admin_credentials(
        "Admin@Example.com",
        password,
    )

    assert email == "admin@example.com"
    assert password_hash != password
    assert verify_password(password, password_hash)


def test_password_hash_is_salted():
    password = "Secure-Admin-Passphrase-2026"

    _, first = prepare_admin_credentials(
        "admin@example.com",
        password,
    )

    _, second = prepare_admin_credentials(
        "admin@example.com",
        password,
    )

    assert first != second
    assert verify_password(password, first)
    assert verify_password(password, second)
