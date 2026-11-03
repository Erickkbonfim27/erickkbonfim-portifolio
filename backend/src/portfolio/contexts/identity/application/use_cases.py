from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

from portfolio.contexts.identity.application.ports import (
    Clock,
    IdentityUnitOfWork,
    PasswordHasher,
    TokenGenerator,
)
from portfolio.contexts.identity.domain.admin import AdminUser, LockoutPolicy
from portfolio.contexts.identity.domain.credentials import Email, check_password_strength
from portfolio.contexts.identity.domain.errors import (
    AccountLockedError,
    AdminAlreadyExistsError,
    InvalidCredentialsError,
    InvalidEmailError,
    SessionInvalidError,
)
from portfolio.contexts.identity.domain.session import AdminSession, hash_token

UnitOfWorkFactory = Callable[[], IdentityUnitOfWork]


@dataclass(frozen=True, slots=True)
class CreateAdmin:
    uow: UnitOfWorkFactory
    hasher: PasswordHasher
    clock: Clock

    async def __call__(self, email: str, password: str) -> AdminUser:
        parsed = Email.parse(email)
        check_password_strength(password)
        async with self.uow() as uow:
            if await uow.admins.get_by_email(parsed) is not None:
                raise AdminAlreadyExistsError(str(parsed))
            admin = AdminUser(
                id=uuid4(),
                email=parsed,
                password_hash=self.hasher.hash(password),
                created_at=self.clock.now(),
            )
            await uow.admins.add(admin)
            await uow.commit()
        return admin


@dataclass(frozen=True, slots=True)
class LoginResult:
    token: str
    expires_at: datetime
    lifetime_seconds: int


@dataclass(frozen=True, slots=True)
class Login:
    uow: UnitOfWorkFactory
    hasher: PasswordHasher
    tokens: TokenGenerator
    clock: Clock
    session_ttl: timedelta
    # Hash of a random secret, verified against when the email is unknown so the
    # response takes as long as a real check and does not reveal which emails exist.
    dummy_password_hash: str
    policy: LockoutPolicy = field(default_factory=LockoutPolicy)

    async def __call__(self, email: str, password: str) -> LoginResult:
        now = self.clock.now()
        async with self.uow() as uow:
            admin = await self._find(uow, email)
            if admin is None:
                self.hasher.verify(self.dummy_password_hash, password)
                raise InvalidCredentialsError
            if admin.locked_until is not None and admin.is_locked(now):
                raise AccountLockedError(admin.locked_until)
            if not self.hasher.verify(admin.password_hash, password):
                await uow.admins.save(admin.with_failed_attempt(now, self.policy))
                await uow.commit()
                raise InvalidCredentialsError

            password_hash = admin.password_hash
            if self.hasher.needs_rehash(password_hash):
                password_hash = self.hasher.hash(password)
            await uow.admins.save(admin.with_successful_login(password_hash))

            token = self.tokens.new_token()
            session = AdminSession(
                id=uuid4(),
                admin_id=admin.id,
                token_hash=hash_token(token),
                created_at=now,
                expires_at=now + self.session_ttl,
            )
            await uow.sessions.add(session)
            await uow.commit()
        lifetime = int((session.expires_at - session.created_at).total_seconds())
        return LoginResult(token=token, expires_at=session.expires_at, lifetime_seconds=lifetime)

    @staticmethod
    async def _find(uow: IdentityUnitOfWork, email: str) -> AdminUser | None:
        try:
            parsed = Email.parse(email)
        except InvalidEmailError:
            return None
        return await uow.admins.get_by_email(parsed)


@dataclass(frozen=True, slots=True)
class Logout:
    uow: UnitOfWorkFactory

    async def __call__(self, token: str) -> None:
        async with self.uow() as uow:
            session = await uow.sessions.get_by_token_hash(hash_token(token))
            if session is None:
                return
            await uow.sessions.delete(session.id)
            await uow.commit()


@dataclass(frozen=True, slots=True)
class Authenticate:
    uow: UnitOfWorkFactory
    clock: Clock

    async def __call__(self, token: str) -> AdminUser:
        async with self.uow() as uow:
            session = await uow.sessions.get_by_token_hash(hash_token(token))
            if session is None:
                raise SessionInvalidError
            if session.is_expired(self.clock.now()):
                await uow.sessions.delete(session.id)
                await uow.commit()
                raise SessionInvalidError
            admin = await uow.admins.get(session.admin_id)
            if admin is None:
                raise SessionInvalidError
            return admin


@dataclass(frozen=True, slots=True)
class IdentityUseCases:
    """What the interfaces (HTTP, CLI) of this context are allowed to call."""

    create_admin: CreateAdmin
    login: Login
    logout: Logout
    authenticate: Authenticate
