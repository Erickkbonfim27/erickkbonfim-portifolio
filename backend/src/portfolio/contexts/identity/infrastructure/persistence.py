from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from portfolio.contexts.identity.domain.admin import AdminUser
from portfolio.contexts.identity.domain.credentials import Email
from portfolio.contexts.identity.domain.session import AdminSession
from portfolio.contexts.identity.infrastructure.models import AdminSessionRow, AdminUserRow


def _to_admin(row: AdminUserRow) -> AdminUser:
    return AdminUser(
        id=row.id,
        email=Email(row.email),
        password_hash=row.password_hash,
        created_at=row.created_at,
        failed_attempts=row.failed_attempts,
        locked_until=row.locked_until,
    )


def _to_session(row: AdminSessionRow) -> AdminSession:
    return AdminSession(
        id=row.id,
        admin_id=row.admin_id,
        token_hash=row.token_hash,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


class SqlAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, admin_id: UUID) -> AdminUser | None:
        row = await self._session.get(AdminUserRow, admin_id)
        return _to_admin(row) if row is not None else None

    async def get_by_email(self, email: Email) -> AdminUser | None:
        row = await self._session.scalar(
            select(AdminUserRow).where(AdminUserRow.email == email.value)
        )
        return _to_admin(row) if row is not None else None

    async def add(self, admin: AdminUser) -> None:
        self._session.add(
            AdminUserRow(
                id=admin.id,
                email=admin.email.value,
                password_hash=admin.password_hash,
                failed_attempts=admin.failed_attempts,
                locked_until=admin.locked_until,
                created_at=admin.created_at,
            )
        )

    async def save(self, admin: AdminUser) -> None:
        row = await self._session.get_one(AdminUserRow, admin.id)
        row.email = admin.email.value
        row.password_hash = admin.password_hash
        row.failed_attempts = admin.failed_attempts
        row.locked_until = admin.locked_until


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: AdminSession) -> None:
        self._session.add(
            AdminSessionRow(
                id=session.id,
                admin_id=session.admin_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                expires_at=session.expires_at,
            )
        )

    async def get_by_token_hash(self, token_hash: str) -> AdminSession | None:
        row = await self._session.scalar(
            select(AdminSessionRow).where(AdminSessionRow.token_hash == token_hash)
        )
        return _to_session(row) if row is not None else None

    async def delete(self, session_id: UUID) -> None:
        await self._session.execute(delete(AdminSessionRow).where(AdminSessionRow.id == session_id))


class SqlIdentityUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.admins = SqlAdminRepository(self._session)
        self.sessions = SqlSessionRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Anything not committed is discarded; close() rolls back the open transaction.
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
