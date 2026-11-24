"""Local administrator provisioning helpers.

No public registration endpoint.
No database access or automatic account creation.
"""

from pydantic import EmailStr, TypeAdapter, ValidationError

from .auth import hash_password


MIN_ADMIN_PASSWORD_LENGTH = 12
MAX_ADMIN_PASSWORD_BYTES = 72

_email_adapter = TypeAdapter(EmailStr)


class AdminProvisioningError(ValueError):
    """Rejected administrator provisioning input."""


def normalize_admin_email(email: str) -> str:
    """Validate and normalize an administrator email address."""

    if not isinstance(email, str):
        raise AdminProvisioningError("Invalid admin email")

    try:
        normalized = str(
            _email_adapter.validate_python(email.strip())
        ).lower()
    except (ValidationError, ValueError, TypeError):
        raise AdminProvisioningError(
            "Invalid admin email"
        ) from None

    if len(normalized) > 255:
        raise AdminProvisioningError(
            "Admin email exceeds maximum length"
        )

    return normalized


def validate_admin_password(password: str) -> None:
    """Enforce conservative password input boundaries."""

    if not isinstance(password, str):
        raise AdminProvisioningError(
            "Invalid administrator password"
        )

    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise AdminProvisioningError(
            "Administrator password is too short"
        )

    if len(password.encode("utf-8")) > MAX_ADMIN_PASSWORD_BYTES:
        raise AdminProvisioningError(
            "Administrator password exceeds byte limit"
        )

    if any(ord(char) < 32 or ord(char) == 127 for char in password):
        raise AdminProvisioningError(
            "Administrator password contains control characters"
        )


def prepare_admin_credentials(
    email: str,
    password: str,
) -> tuple[str, str]:
    """Return normalized email and securely hashed password.

    The caller is responsible for authorization, database
    transaction safety and secret handling.
    """

    normalized_email = normalize_admin_email(email)
    validate_admin_password(password)

    password_hash = hash_password(password)

    return normalized_email, password_hash
