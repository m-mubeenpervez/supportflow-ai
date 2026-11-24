"""Encryption for queued verification tokens.

Uses authenticated Fernet encryption.
Keys must be supplied through protected configuration.
"""

from cryptography.fernet import Fernet, InvalidToken

from .email_verification import hash_token


def encrypt_token(raw_token: str, key: str) -> str:
    """Encrypt a validated verification token."""

    hash_token(raw_token)

    if not isinstance(key, str):
        raise ValueError("Invalid encryption key")

    try:
        cipher = Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid encryption key") from exc

    encrypted = cipher.encrypt(
        raw_token.encode("ascii")
    )

    return encrypted.decode("ascii")


def decrypt_token(encrypted_token: str, key: str) -> str:
    """Decrypt and validate an encrypted token."""

    if (
        not isinstance(encrypted_token, str)
        or not isinstance(key, str)
    ):
        raise ValueError("Invalid encrypted token or key")

    try:
        cipher = Fernet(key.encode("ascii"))
        raw_token = cipher.decrypt(
            encrypted_token.encode("ascii")
        ).decode("ascii")

        hash_token(raw_token)

    except (
        InvalidToken,
        ValueError,
        TypeError,
        UnicodeError,
    ) as exc:
        raise ValueError(
            "Verification token decryption failed"
        ) from exc

    return raw_token
