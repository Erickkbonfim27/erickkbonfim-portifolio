import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


def hash_token(token: str) -> str:
    """Only the hash of a session token is stored, so a database leak yields no usable cookie.

    SHA-256 without salt is enough here: the token is 256 bits of randomness, not a
    password, so there is nothing to brute force.
    """
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AdminSession:
    id: UUID
    admin_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
