"""No-network tests for encrypted verification tokens."""

import pytest
from cryptography.fernet import Fernet

from app.email_verification import issue_challenge
from app.verification_email_crypto import (
    decrypt_token,
    encrypt_token,
)


def make_key():
    return Fernet.generate_key().decode("ascii")


def test_encrypt_and_decrypt_round_trip():
    token = issue_challenge().raw_token
    key = make_key()

    encrypted = encrypt_token(token, key)

    assert decrypt_token(encrypted, key) == token


def test_encrypted_payload_does_not_contain_raw_token():
    token = issue_challenge().raw_token
    encrypted = encrypt_token(token, make_key())

    assert token not in encrypted
    assert encrypted != token


def test_encryption_uses_randomized_ciphertext():
    token = issue_challenge().raw_token
    key = make_key()

    first = encrypt_token(token, key)
    second = encrypt_token(token, key)

    assert first != second
    assert decrypt_token(first, key) == token
    assert decrypt_token(second, key) == token


def test_wrong_key_rejected():
    token = issue_challenge().raw_token
    encrypted = encrypt_token(token, make_key())

    with pytest.raises(ValueError):
        decrypt_token(encrypted, make_key())


def test_tampered_ciphertext_rejected():
    token = issue_challenge().raw_token
    key = make_key()

    encrypted = encrypt_token(token, key)

    tampered = (
        encrypted[:20]
        + ("A" if encrypted[20] != "A" else "B")
        + encrypted[21:]
    )

    with pytest.raises(ValueError):
        decrypt_token(tampered, key)


def test_invalid_raw_token_rejected():
    with pytest.raises(ValueError):
        encrypt_token("invalid-token", make_key())


def test_invalid_encryption_key_rejected():
    token = issue_challenge().raw_token

    with pytest.raises(ValueError):
        encrypt_token(token, "incorrect-key")


def test_invalid_encrypted_input_rejected():
    with pytest.raises(ValueError):
        decrypt_token("invalid-ciphertext", make_key())


def test_ciphertext_does_not_decrypt_without_key():
    token = issue_challenge().raw_token

    first_key = make_key()
    second_key = make_key()

    encrypted = encrypt_token(token, first_key)

    with pytest.raises(ValueError):
        decrypt_token(encrypted, second_key)
