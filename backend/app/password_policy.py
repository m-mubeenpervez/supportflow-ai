"""Password strength validation for account password changes."""


def password_policy_errors(password: str) -> list[str]:
    if not isinstance(password, str):
        return ["Invalid password"]

    errors = []

    if not 12 <= len(password) <= 128:
        errors.append("12 to 128 characters required")

    if not any("A" <= c <= "Z" for c in password):
        errors.append("Uppercase letter required")

    if not any("a" <= c <= "z" for c in password):
        errors.append("Lowercase letter required")

    if not any("0" <= c <= "9" for c in password):
        errors.append("Number required")

    if not any(c in "!@#$" for c in password):
        errors.append("Special character (!@#$) required")

    return errors
