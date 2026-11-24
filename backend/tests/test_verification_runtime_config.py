"""Pure tests for verification email runtime configuration."""

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.verification_runtime_config import (
    get_verification_email_config,
)


def make_config(key=None, url=None):
    return SimpleNamespace(
        verification_email_encryption_key=(
            key if key is not None
            else Fernet.generate_key().decode("ascii")
        ),
        verification_email_base_url=(
            url if url is not None
            else "http://localhost:5173/verify-email"
        ),
    )


def test_settings_fields_exist():
    fields = Settings.model_fields
    assert "verification_email_encryption_key" in fields
    assert "verification_email_base_url" in fields


def test_valid_runtime_configuration():
    config = make_config()
    result = get_verification_email_config(config)

    assert result.encryption_key == (
        config.verification_email_encryption_key
    )
    assert result.base_url == config.verification_email_base_url


def test_missing_key_rejected():
    config = make_config()
    config.verification_email_encryption_key = ""

    with pytest.raises(RuntimeError):
        get_verification_email_config(config)


def test_invalid_key_rejected():
    with pytest.raises(RuntimeError):
        get_verification_email_config(
            make_config(key="not-a-fernet-key")
        )


def test_missing_url_rejected():
    config = make_config()
    config.verification_email_base_url = ""

    with pytest.raises(RuntimeError):
        get_verification_email_config(config)


def test_insecure_remote_http_rejected():
    with pytest.raises(RuntimeError):
        get_verification_email_config(
            make_config(
                url="http://example.com/verify-email"
            )
        )


def test_https_url_accepted():
    result = get_verification_email_config(
        make_config(
            url="https://example.com/verify-email"
        )
    )
    assert result.base_url.startswith("https://")
