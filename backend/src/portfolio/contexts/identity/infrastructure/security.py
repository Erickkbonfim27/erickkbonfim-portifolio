import secrets

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from portfolio.platform.clock import SystemClock

__all__ = ["Argon2PasswordHasher", "SystemClock", "UrlSafeTokenGenerator"]


class Argon2PasswordHasher:
    """Argon2id with the library's current defaults (RFC 9106 low-memory profile).

    When the library raises its defaults, `needs_rehash` is true for old hashes and
    the login use case upgrades them transparently, with no password reset.
    """

    def __init__(self, argon2: Argon2 | None = None) -> None:
        self._argon2 = argon2 or Argon2()

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._argon2.check_needs_rehash(password_hash)


class UrlSafeTokenGenerator:
    def new_token(self) -> str:
        return secrets.token_urlsafe(32)
