from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from sqlalchemy import DateTime, String, Text, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from portfolio.contexts.contacts.domain.model import (
    ContactForm,
    ContactRequest,
    ContactStatus,
    DuplicateSubmissionError,
    Lang,
)
from portfolio.platform.db import Base
from portfolio.platform.outbox import add_event


class ContactRow(Base):
    __tablename__ = "contacts_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(String(120))
    lang: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(10), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thanked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _to_request(row: ContactRow) -> ContactRequest:
    lang: Lang = "pt" if row.lang == "pt" else "en"
    return ContactRequest(
        id=row.id,
        form=ContactForm(row.name, row.contact, row.brief, row.company, lang),
        status=ContactStatus(row.status),
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
        notified_at=row.notified_at,
        thanked_at=row.thanked_at,
    )


class SqlContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, contact_id: UUID) -> ContactRequest | None:
        row = await self._session.get(ContactRow, contact_id)
        return _to_request(row) if row is not None else None

    async def get_by_idempotency_key(self, key: str) -> ContactRequest | None:
        row = await self._session.scalar(
            select(ContactRow).where(ContactRow.idempotency_key == key)
        )
        return _to_request(row) if row is not None else None

    async def list(self, status: ContactStatus | None) -> list[ContactRequest]:
        statement = select(ContactRow).order_by(ContactRow.created_at.desc())
        if status is not None:
            statement = statement.where(ContactRow.status == status.value)
        return [_to_request(row) for row in await self._session.scalars(statement)]

    async def add(self, request: ContactRequest) -> None:
        form = request.form
        self._session.add(
            ContactRow(
                id=request.id,
                name=form.name,
                contact=form.contact,
                brief=form.brief,
                company=form.company,
                lang=form.lang,
                status=request.status.value,
                idempotency_key=request.idempotency_key,
                created_at=request.created_at,
                notified_at=request.notified_at,
                thanked_at=request.thanked_at,
            )
        )

    async def save(self, request: ContactRequest) -> None:
        row = await self._session.get_one(ContactRow, request.id)
        row.status = request.status.value
        row.notified_at = request.notified_at
        row.thanked_at = request.thanked_at

    async def delete(self, contact_id: UUID) -> None:
        await self._session.execute(delete(ContactRow).where(ContactRow.id == contact_id))

    async def thanked_since(self, email: str, since: datetime) -> bool:
        statement = select(ContactRow.id).where(
            func.lower(func.trim(ContactRow.contact)) == email, ContactRow.thanked_at >= since
        )
        return await self._session.scalar(statement.limit(1)) is not None

    async def delete_created_before(self, cutoff: datetime) -> int:
        result = await self._session.execute(
            delete(ContactRow).where(ContactRow.created_at < cutoff)
        )
        return int(getattr(result, "rowcount", 0) or 0)


class SqlContactsUnitOfWork:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], now: Callable[[], datetime]
    ) -> None:
        self._session_factory = session_factory
        self._now = now

    @property
    def contacts(self) -> SqlContactRepository:
        return self._contacts

    def record(self, topic: str, payload: dict[str, Any]) -> None:
        add_event(self._session, topic, payload, self._now())

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._contacts = SqlContactRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._session.close()

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            if "uq_contacts_requests_idempotency_key" in str(error.orig):
                raise DuplicateSubmissionError from error
            raise
