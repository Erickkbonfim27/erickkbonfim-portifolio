from datetime import datetime

# The email rule lives in the shared kernel; re-exported so callers of this
# context keep a single place to import its errors from.
from portfolio.kernel.email import InvalidEmailError

__all__ = [
    "AccountLockedError",
    "AdminAlreadyExistsError",
    "IdentityError",
    "InvalidCredentialsError",
    "InvalidEmailError",
    "SessionInvalidError",
    "WeakPasswordError",
]


class IdentityError(Exception):
    """Base class for every identity rule violation."""


class WeakPasswordError(IdentityError):
    pass


class AdminAlreadyExistsError(IdentityError):
    pass


class InvalidCredentialsError(IdentityError):
    """Wrong email or password. Deliberately does not say which."""


class AccountLockedError(IdentityError):
    def __init__(self, until: datetime) -> None:
        super().__init__(f"account locked until {until.isoformat()}")
        self.until = until


class SessionInvalidError(IdentityError):
    """Missing, unknown or expired session."""
