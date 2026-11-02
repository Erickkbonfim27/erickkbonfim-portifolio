from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from portfolio.contexts.contacts.application.ports import (
    Clock,
    ContactsUnitOfWork,
    Mailer,
    RateLimiter,
)
from portfolio.contexts.contacts.domain.model import (
    ContactForm,
    ContactNotFoundError,
    ContactRequest,
    ContactStatus,
    DuplicateSubmissionError,
    TooManyRequestsError,
    owner_notification,
    retention_cutoff,
    thank_you,
)

UnitOfWorkFactory = Callable[[], ContactsUnitOfWork]

CONTACT_RECEIVED = "contact.received"
SUBMISSIONS_PER_DAY = 5
DAY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class SubmitContact:
    uow: UnitOfWorkFactory
    limiter: RateLimiter
    clock: Clock

    async def __call__(
        self, form: ContactForm, client: str, idempotency_key: str | None, honeypot: str = ""
    ) -> UUID:
        if honeypot:
            # A bot filled the hidden field: answer like a success, store nothing.
            return uuid4()
        if idempotency_key:
            existing = await self._existing(idempotency_key)
            if existing is not None:
                return existing
        if not await self.limiter.hit("contact", client, SUBMISSIONS_PER_DAY, DAY):
            raise TooManyRequestsError(f"at most {SUBMISSIONS_PER_DAY} messages per day")
        request = ContactRequest(
            id=uuid4(),
            form=form,
            status=ContactStatus.NEW,
            idempotency_key=idempotency_key,
            created_at=self.clock.now(),
        )
        try:
            async with self.uow() as uow:
                await uow.contacts.add(request)
                uow.record(CONTACT_RECEIVED, {"id": str(request.id)})
                await uow.commit()
        except DuplicateSubmissionError:
            # Two retries with the same key raced; the other one stored it.
            existing = await self._existing(idempotency_key) if idempotency_key else None
            if existing is None:
                raise
            return existing
        return request.id

    async def _existing(self, idempotency_key: str) -> UUID | None:
        async with self.uow() as uow:
            found = await uow.contacts.get_by_idempotency_key(idempotency_key)
        return found.id if found is not None else None


@dataclass(frozen=True, slots=True)
class NotifyContact:
    """Handles `contact.received`. Idempotent: each email is sent at most once per contact,
    and each send is committed on its own so a retry does not repeat the previous one.

    The thank-you is limited to one per address per day, decided from what was actually
    sent (not from a counter), so a failed send never uses up that address's quota.
    """

    uow: UnitOfWorkFactory
    mailer: Mailer
    clock: Clock
    owner_email: str

    async def __call__(self, contact_id: UUID) -> None:
        async with self.uow() as uow:
            request = await uow.contacts.get(contact_id)
            if request is None:
                return  # deleted before we got to it
            if request.notified_at is None:
                await self.mailer.send(owner_notification(self.owner_email, request))
                request = request.notified(self.clock.now())
                await uow.contacts.save(request)
                await uow.commit()
            reply = request.reply_email()
            if reply is None or request.thanked_at is not None:
                return
            now = self.clock.now()
            # The form cannot be used to flood someone's mailbox from this domain.
            if await uow.contacts.thanked_since(reply.value, now - DAY):
                return
            await self.mailer.send(thank_you(reply, request.form.lang))
            await uow.contacts.save(request.thanked(now))
            await uow.commit()


@dataclass(frozen=True, slots=True)
class ListContacts:
    uow: UnitOfWorkFactory

    async def __call__(self, status: ContactStatus | None = None) -> list[ContactRequest]:
        async with self.uow() as uow:
            return await uow.contacts.list(status)


@dataclass(frozen=True, slots=True)
class GetContact:
    uow: UnitOfWorkFactory

    async def __call__(self, contact_id: UUID) -> ContactRequest:
        async with self.uow() as uow:
            request = await uow.contacts.get(contact_id)
        if request is None:
            raise ContactNotFoundError(contact_id)
        return request


@dataclass(frozen=True, slots=True)
class SetContactStatus:
    uow: UnitOfWorkFactory

    async def __call__(self, contact_id: UUID, status: ContactStatus) -> ContactRequest:
        async with self.uow() as uow:
            request = await uow.contacts.get(contact_id)
            if request is None:
                raise ContactNotFoundError(contact_id)
            request = request.with_status(status)
            await uow.contacts.save(request)
            await uow.commit()
        return request


@dataclass(frozen=True, slots=True)
class DeleteContact:
    uow: UnitOfWorkFactory

    async def __call__(self, contact_id: UUID) -> None:
        async with self.uow() as uow:
            if await uow.contacts.get(contact_id) is None:
                raise ContactNotFoundError(contact_id)
            await uow.contacts.delete(contact_id)
            await uow.commit()


@dataclass(frozen=True, slots=True)
class PurgeExpiredContacts:
    """Daily job: delete contact requests older than the retention period."""

    uow: UnitOfWorkFactory
    clock: Clock

    async def __call__(self) -> str:
        async with self.uow() as uow:
            deleted = await uow.contacts.delete_created_before(retention_cutoff(self.clock.now()))
            await uow.commit()
        return f"deleted {deleted} expired contacts"


@dataclass(frozen=True, slots=True)
class ContactsUseCases:
    submit: SubmitContact
    list: ListContacts
    get: GetContact
    set_status: SetContactStatus
    delete: DeleteContact
    purge_expired: PurgeExpiredContacts
