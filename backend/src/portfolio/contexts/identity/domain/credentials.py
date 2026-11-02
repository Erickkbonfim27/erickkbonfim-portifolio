"""Email and password rules. Pure functions, no I/O."""

from portfolio.contexts.identity.domain.errors import WeakPasswordError
from portfolio.kernel.email import Email

__all__ = ["MAX_PASSWORD_LENGTH", "MIN_PASSWORD_LENGTH", "Email", "check_password_strength"]

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def check_password_strength(password: str) -> None:
    """Length is the rule that matters; composition rules push people to `Passw0rd!`."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"password must have at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        # Argon2 handles long input, but an unbounded field is a cheap DoS vector.
        raise WeakPasswordError(f"password must have at most {MAX_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        raise WeakPasswordError("password must not start or end with whitespace")
