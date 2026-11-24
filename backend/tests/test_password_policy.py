import pytest

from app.password_policy import password_policy_errors


@pytest.mark.parametrize("password", [
    "ValidPassword1!",
    "AnotherStrong9@",
    "ExampleSecure7#",
    "GoodPassword4$",
])
def test_accepts_strong_password(password):
    assert password_policy_errors(password) == []


@pytest.mark.parametrize("password", [
    "Short1!",
    "lowercase123!",
    "UPPERCASE123!",
    "NoNumbersHere!",
    "NoSpecial1234",
    "",
    "ValidPassword1%",
])
def test_rejects_weak_password(password):
    assert password_policy_errors(password)


def test_rejects_too_long_password():
    password = "A" + "a" * 126 + "1!"
    assert len(password) == 129
    assert password_policy_errors(password)


def test_accepts_minimum_length():
    assert password_policy_errors("Abcdefghij1!") == []


def test_rejects_non_string_input():
    assert password_policy_errors(None)
