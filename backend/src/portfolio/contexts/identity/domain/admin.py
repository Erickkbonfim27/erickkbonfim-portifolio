from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from portfolio.contexts.identity.domain.credentials import Email


@dataclass(frozen=True, slots=True)
class LockoutPolicy:
    """Progressive lockout: free attempts first, then the lock doubles on every failure.

    With the defaults, the 5th wrong password locks for 1 minute, the 6th for 2,
    the 7th for 4, and so on up to 1 hour. A correct password resets the count.
    """

    free_attempts: int = 4
    base_lock: timedelta = timedelta(minutes=1)
    max_lock: timedelta = timedelta(hours=1)

    def lock_duration(self, failed_attempts: int) -> timedelta | None:
        if failed_attempts <= self.free_attempts:
            return None
        exponent = failed_attempts - self.free_attempts - 1
        # Cap the exponent before multiplying so a huge counter cannot overflow timedelta.
        capped = min(exponent, 32)
        return min(self.base_lock * (1 << capped), self.max_lock)


@dataclass(frozen=True, slots=True)
class AdminUser:
    id: UUID
    email: Email
    password_hash: str
    created_at: datetime
    failed_attempts: int = 0
    locked_until: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def with_failed_attempt(self, now: datetime, policy: LockoutPolicy) -> "AdminUser":
        attempts = self.failed_attempts + 1
        lock = policy.lock_duration(attempts)
        return replace(
            self,
            failed_attempts=attempts,
            locked_until=now + lock if lock is not None else None,
        )

    def with_successful_login(self, password_hash: str) -> "AdminUser":
        return replace(self, failed_attempts=0, locked_until=None, password_hash=password_hash)
