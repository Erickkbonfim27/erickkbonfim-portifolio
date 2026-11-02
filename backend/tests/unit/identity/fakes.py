from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID

from portfolio.contexts.identity.application.use_cases import (
    Authenticate,
    CreateAdmin,
    IdentityUseCases,
    Login,
    Logout,
)
from portfolio.contexts.identity.domain.admin import AdminUser
from portfolio.contexts.identity.domain.credentials import Email
from portfolio.contexts.identity.domain.session import AdminSession

START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@dataclass
class Store:
    """The 'database' shared by every unit of work of one test."""

    admins: dict[UUID, AdminUser] = field(default_factory=dict)
    sessions: dict[UUID, AdminSession] = field(default_factory=dict)
    commits: int = 0


class InMemoryAdmins:
    def __init__(self, staged: dict[UUID, AdminUser]) -> None:
        self._staged = staged

    async def get(self, admin_id: UUID) -> AdminUser | None:
        return self._staged.get(admin_id)

    async def get_by_email(self, email: Email) -> AdminUser | None:
        return next((a for a in self._staged.values() if a.email == email), None)

    async def add(self, admin: AdminUser) -> None:
        self._staged[admin.id] = admin

    async def save(self, admin: AdminUser) -> None:
        self._staged[admin.id] = admin


class InMemorySessions:
    def __init__(self, staged: dict[UUID, AdminSession]) -> None:
        self._staged = staged

    async def add(self, session: AdminSession) -> None:
        self._staged[session.id] = session

    async def get_by_token_hash(self, token_hash: str) -> AdminSession | None:
        return next((s for s in self._staged.values() if s.token_hash == token_hash), None)

    async def delete(self, session_id: UUID) -> None:
        self._staged.pop(session_id, None)


class InMemoryUnitOfWork:
    """Works on a copy of the store and publishes it only on commit, like a transaction."""

    def __init__(self, store: Store) -> None:
        self._store = store

    async def __aenter__(self) -> Self:
        self._admins = dict(self._store.admins)
        self._sessions = dict(self._store.sessions)
        self.admins = InMemoryAdmins(self._admins)
        self.sessions = InMemorySessions(self._sessions)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self._store.admins = dict(self._admins)
        self._store.sessions = dict(self._sessions)
        self._store.commits += 1


class FakeHasher:
    """Reversible on purpose: tests read the hash to know what was hashed."""

    def __init__(self) -> None:
        self.outdated: set[str] = set()
        self.verified: list[str] = []
        self.accept_any = False

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        self.verified.append(password_hash)
        return self.accept_any or password_hash == f"hashed:{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return password_hash in self.outdated


class FixedClock:
    def __init__(self, now: datetime = START) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class SequentialTokens:
    def __init__(self) -> None:
        self.count = 0

    def new_token(self) -> str:
        self.count += 1
        return f"token-{self.count}"


DUMMY_HASH = "hashed:dummy-secret-nobody-knows"
SESSION_TTL = timedelta(hours=12)


@dataclass
class Harness:
    store: Store
    hasher: FakeHasher
    clock: FixedClock
    tokens: SequentialTokens
    use_cases: IdentityUseCases


def make_harness() -> Harness:
    store, hasher, clock, tokens = Store(), FakeHasher(), FixedClock(), SequentialTokens()

    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    use_cases = IdentityUseCases(
        create_admin=CreateAdmin(uow=uow, hasher=hasher, clock=clock),
        login=Login(
            uow=uow,
            hasher=hasher,
            tokens=tokens,
            clock=clock,
            session_ttl=SESSION_TTL,
            dummy_password_hash=DUMMY_HASH,
        ),
        logout=Logout(uow=uow),
        authenticate=Authenticate(uow=uow, clock=clock),
    )
    return Harness(store, hasher, clock, tokens, use_cases)
