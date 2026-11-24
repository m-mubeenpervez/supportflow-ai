"""Security regression tests for verification email links.

Pure URL tests: no network, SMTP, database, or external APIs.
"""

import pytest
from urllib.parse import parse_qs, urlsplit

from app.email_verification import issue_challenge
from app.verification_delivery_processor import (
    build_verification_url,
)


def token():
    return issue_challenge().raw_token


def test_https_verification_url():
    raw = token()

    result = build_verification_url(
        "https://support.example.com/verify-email",
        raw,
    )

    parsed = urlsplit(result)

    assert parsed.scheme == "https"
    assert parsed.hostname == "support.example.com"
    assert parsed.path == "/verify-email"
    assert parse_qs(parsed.query) == {"token": [raw]}


def test_localhost_http_allowed_for_development():
    raw = token()

    result = build_verification_url(
        "http://localhost:5173/verify-email",
        raw,
    )

    assert result == (
        "http://localhost:5173/verify-email?token="
        + raw
    )


def test_loopback_ip_allowed_for_development():
    raw = token()

    result = build_verification_url(
        "http://127.0.0.1:5173/verify-email",
        raw,
    )

    assert urlsplit(result).hostname == "127.0.0.1"


def test_default_verification_path():
    result = build_verification_url(
        "https://support.example.com",
        token(),
    )

    assert urlsplit(result).path == "/verify-email"


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://support.example.com/verify-email",
        "http://localhost.evil.com/verify-email",
        "https://user:password@support.example.com/verify-email",
        "https://support.example.com/verify-email?other=value",
        "https://support.example.com/verify-email#fragment",
        "javascript:alert(1)",
        "https://support.example.com/verify-email\nInjected",
        "https://support.example.com/verify-email with space",
        "ftp://support.example.com/verify-email",
    ],
)
def test_unsafe_url_rejected(unsafe_url):
    with pytest.raises(ValueError):
        build_verification_url(unsafe_url, token())


@pytest.mark.parametrize(
    "invalid_token",
    [
        "",
        "invalid",
        "a" * 42,
        "a" * 44,
        "a" * 42 + "!",
    ],
)
def test_invalid_token_rejected(invalid_token):
    with pytest.raises(ValueError):
        build_verification_url(
            "https://support.example.com/verify-email",
            invalid_token,
        )


def test_token_only_appears_in_query():
    raw = token()

    result = build_verification_url(
        "https://support.example.com/verify-email",
        raw,
    )

    parsed = urlsplit(result)

    assert raw not in parsed.path
    assert raw not in parsed.netloc
    assert parsed.fragment == ""
    assert parse_qs(parsed.query)["token"] == [raw]
