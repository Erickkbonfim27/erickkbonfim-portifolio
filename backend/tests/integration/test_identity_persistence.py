from datetime import timedelta
from uuid import uuid4

import pytest
from argon2 import PasswordHasher as Argon2
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from portfolio.contexts.identity.application.use_cases import (
    Authenticate,
    CreateAdmin,
    Login,
    Logout,
)
from portfolio.contexts.identity.domain.admin import AdminUser, LockoutPolicy
from portfolio.contexts.identity.domain.credentials import Email
from portfolio.contexts.identity.domain.errors import SessionInvalidError
from portfolio.contexts.identity.domain.session import AdminSession
from portfolio.contexts.identity.infrastructure.persistence import SqlIdentityUnitOfWork
from portfolio.contexts.identity.infrastructure.security import (
    Argon2PasswordHasher,
    SystemClock,
    UrlSafeTokenGenerator,
)
from tests.unit.identity.fakes import START

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


def _admin(email: str = "erick@example.dev") -> AdminUser:
    return AdminUser(id=uuid4(), email=Email.parse(email), password_hash="h", created_at=START)


async def test_admin_round_trip(session_factory: Factory) -> None:
    admin = _admin()
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        await uow.admins.add(admin)
        await uow.commit()
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        assert await uow.admins.get(admin.id) == admin
        assert await uow.admins.get_by_email(admin.email) == admin
        assert await uow.admins.get(uuid4()) is None
        assert await uow.admins.get_by_email(Email.parse("ghost@example.dev")) is None


async def test_save_updates_lockout_state(session_factory: Factory) -> None:
    admin = _admin()
    locked = admin.with_failed_attempt(START, LockoutPolicy(free_attempts=0))
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        await uow.admins.add(admin)
        await uow.admins.save(locked)
        await uow.commit()
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        assert await uow.admins.get(admin.id) == locked


async def test_email_is_unique(session_factory: Factory) -> None:
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        await uow.admins.add(_admin())
        await uow.admins.add(_admin())
        with pytest.raises(IntegrityError):
            await uow.commit()


async def test_uncommitted_work_is_discarded(session_factory: Factory) -> None:
    admin = _admin()
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        await uow.admins.add(admin)
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        assert await uow.admins.get(admin.id) is None


async def test_session_round_trip_and_delete(session_factory: Factory) -> None:
    admin = _admin()
    session = AdminSession(uuid4(), admin.id, "a" * 64, START, START + timedelta(hours=1))
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        await uow.admins.add(admin)
        await uow.sessions.add(session)
        await uow.commit()
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        assert await uow.sessions.get_by_token_hash("a" * 64) == session
        await uow.sessions.delete(session.id)
        await uow.commit()
    async with SqlIdentityUnitOfWork(session_factory) as uow:
        assert await uow.sessions.get_by_token_hash("a" * 64) is None


async def test_full_flow_with_real_adapters(session_factory: Factory) -> None:
    def uow() -> SqlIdentityUnitOfWork:
        return SqlIdentityUnitOfWork(session_factory)

    hasher = Argon2PasswordHasher(Argon2(time_cost=1, memory_cost=8, parallelism=1))
    clock = SystemClock()
    await CreateAdmin(uow, hasher, clock)("erick@example.dev", "correct horse battery staple")
    login = Login(uow, hasher, UrlSafeTokenGenerator(), clock, timedelta(hours=1), hasher.hash("x"))
    result = await login("erick@example.dev", "correct horse battery staple")

    admin = await Authenticate(uow, clock)(result.token)
    assert admin.email.value == "erick@example.dev"

    await Logout(uow)(result.token)
    with pytest.raises(SessionInvalidError):
        await Authenticate(uow, clock)(result.token)
