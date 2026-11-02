import json
from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from portfolio.contexts.contacts.application.use_cases import (
    ContactsUseCases,
    NotifyContact,
)
from portfolio.contexts.contacts.domain.model import (
    ContactForm,
    ContactNotFoundError,
    ContactRequest,
    ContactStatus,
    DuplicateSubmissionError,
    InvalidContactError,
    OutgoingEmail,
    TooManyRequestsError,
    owner_notification,
)
from portfolio.contexts.contacts.infrastructure.mailer import RESEND_URL, ResendMailer
from portfolio.contexts.contacts.interfaces import consumer
from portfolio.platform.messaging import Delivery
from tests.unit.fakes import (
    ContactsStore,
    FakeLimiter,
    FakeMailer,
    contacts_uow_factory,
    contacts_use_cases,
)
from tests.unit.identity.fakes import START, FixedClock
from tests.unit.support import World, make_world
from tests.unit.test_http import login

FORM = ContactForm.build("Ana Recruiter", "ana@corp.dev", "AI Engineer role, remote.", "Corp", "en")
PHONE_FORM = ContactForm.build("Bia", "+55 47 99999-0000", "Vaga de AI Engineer.", None, "pt")


@pytest.fixture
def store() -> ContactsStore:
    return ContactsStore()


@pytest.fixture
def limiter() -> FakeLimiter:
    return FakeLimiter()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def uc(store: ContactsStore, limiter: FakeLimiter, clock: FixedClock) -> ContactsUseCases:
    return contacts_use_cases(store, limiter, clock)


class TestForm:
    @pytest.mark.parametrize(
        ("args", "reason"),
        [
            (("", "a@b.co", "long enough brief", None), "from"),
            (("A", "ab", "long enough brief", None), "contact"),
            (("A", "a@b.co", "short", None), "brief"),
            (("A", "a@b.co", "long enough brief", "c" * 121), "company"),
        ],
    )
    def test_rejects(self, args: tuple[str, str, str, str | None], reason: str) -> None:
        with pytest.raises(InvalidContactError, match=reason):
            ContactForm.build(*args, "en")

    def test_trims_and_drops_empty_company(self) -> None:
        form = ContactForm.build("  A ", " a@b.co ", "  long enough brief ", "  ", "pt")
        assert (form.name, form.contact, form.company) == ("A", "a@b.co", None)

    def test_owner_notification_replies_to_the_sender(self) -> None:
        request = ContactRequest(uuid4(), FORM, ContactStatus.NEW, None, START)
        email = owner_notification("erick@x.dev", request)
        assert (email.to, email.reply_to) == ("erick@x.dev", "ana@corp.dev")
        assert "AI Engineer role, remote." in email.text
        phone = ContactRequest(uuid4(), PHONE_FORM, ContactStatus.NEW, None, START)
        assert owner_notification("erick@x.dev", phone).reply_to is None


class TestSubmit:
    async def test_stores_and_records_an_event(
        self, uc: ContactsUseCases, store: ContactsStore
    ) -> None:
        contact_id = await uc.submit(FORM, "1.2.3.4", None)
        assert store.data[contact_id].status is ContactStatus.NEW
        assert store.events == [("contact.received", {"id": str(contact_id)})]

    async def test_honeypot_pretends_success(
        self, uc: ContactsUseCases, store: ContactsStore, limiter: FakeLimiter
    ) -> None:
        assert isinstance(await uc.submit(FORM, "1.2.3.4", None, honeypot="spam.biz"), UUID)
        assert store.data == {}
        assert not limiter.hits

    async def test_same_idempotency_key_returns_the_same_id(
        self, uc: ContactsUseCases, store: ContactsStore
    ) -> None:
        first = await uc.submit(FORM, "1.2.3.4", "key-1")
        assert await uc.submit(FORM, "1.2.3.4", "key-1") == first
        assert len(store.data) == 1

    async def test_racing_retries_resolve_to_the_stored_one(
        self, uc: ContactsUseCases, store: ContactsStore
    ) -> None:
        winner = ContactRequest(uuid4(), FORM, ContactStatus.NEW, "key-1", START)
        store.race_with = winner
        assert await uc.submit(FORM, "1.2.3.4", "key-1") == winner.id

    async def test_duplicate_without_a_stored_row_is_raised(self, store: ContactsStore) -> None:
        store.race_with = ContactRequest(uuid4(), FORM, ContactStatus.NEW, None, START)
        uc = contacts_use_cases(store, FakeLimiter(), FixedClock())
        with pytest.raises(DuplicateSubmissionError):
            await uc.submit(FORM, "1.2.3.4", None)

    async def test_five_per_day_per_client(self, uc: ContactsUseCases) -> None:
        for _ in range(5):
            await uc.submit(FORM, "1.2.3.4", None)
        with pytest.raises(TooManyRequestsError):
            await uc.submit(FORM, "1.2.3.4", None)
        await uc.submit(FORM, "5.6.7.8", None)


class TestNotify:
    def notify(
        self, store: ContactsStore, mailer: FakeMailer, limiter: FakeLimiter
    ) -> NotifyContact:
        return NotifyContact(contacts_uow_factory(store), mailer, FixedClock(), "e@x.dev")

    async def test_owner_and_thank_you_once(
        self, uc: ContactsUseCases, store: ContactsStore, limiter: FakeLimiter
    ) -> None:
        mailer = FakeMailer()
        notify = self.notify(store, mailer, limiter)
        contact_id = await uc.submit(FORM, "1.2.3.4", None)
        await notify(contact_id)
        await notify(contact_id)  # redelivery: nothing is sent twice
        assert [m.to for m in mailer.sent] == ["e@x.dev", "ana@corp.dev"]
        assert mailer.sent[1].subject == "Thanks for reaching out"
        assert "AI Engineer" not in mailer.sent[1].text  # nothing echoed back
        request = store.data[contact_id]
        assert request.notified_at is not None
        assert request.thanked_at is not None

    async def test_phone_contacts_get_no_email(
        self, uc: ContactsUseCases, store: ContactsStore, limiter: FakeLimiter
    ) -> None:
        mailer = FakeMailer()
        contact_id = await uc.submit(PHONE_FORM, "1.2.3.4", None)
        await self.notify(store, mailer, limiter)(contact_id)
        assert [m.to for m in mailer.sent] == ["e@x.dev"]

    async def test_one_thank_you_per_address_per_day(
        self, uc: ContactsUseCases, store: ContactsStore, limiter: FakeLimiter
    ) -> None:
        mailer = FakeMailer()
        notify = self.notify(store, mailer, limiter)
        for client in ("1.1.1.1", "2.2.2.2"):
            await notify(await uc.submit(FORM, client, None))
        assert [m.to for m in mailer.sent] == ["e@x.dev", "ana@corp.dev", "e@x.dev"]

    async def test_failure_after_owner_email_does_not_resend_it(
        self, uc: ContactsUseCases, store: ContactsStore, limiter: FakeLimiter
    ) -> None:
        mailer = FakeMailer()
        notify = self.notify(store, mailer, limiter)
        contact_id = await uc.submit(FORM, "1.2.3.4", None)
        original_send = mailer.send

        async def fail_on_thanks(email: OutgoingEmail) -> None:
            if email.to != "e@x.dev":
                raise ConnectionError("resend down")
            await original_send(email)

        mailer.send = fail_on_thanks  # type: ignore[method-assign]
        with pytest.raises(ConnectionError):
            await notify(contact_id)
        mailer.send = original_send  # type: ignore[method-assign]
        await notify(contact_id)
        assert [m.to for m in mailer.sent] == ["e@x.dev", "ana@corp.dev"]

    async def test_deleted_contact_is_ignored(self, store: ContactsStore) -> None:
        mailer = FakeMailer()
        await self.notify(store, mailer, FakeLimiter())(uuid4())
        assert mailer.sent == []

    async def test_consumer_handler_parses_the_event(
        self, uc: ContactsUseCases, store: ContactsStore, limiter: FakeLimiter
    ) -> None:
        mailer = FakeMailer()
        contact_id = await uc.submit(PHONE_FORM, "1.2.3.4", None)
        handle = consumer.handler(self.notify(store, mailer, limiter))
        await handle(Delivery("m1", "contact.received", {"id": str(contact_id)}, 1))
        assert len(mailer.sent) == 1
        assert consumer.QUEUE.bindings == ("contact.received",)


class TestAdmin:
    async def test_inbox_flow(self, uc: ContactsUseCases) -> None:
        contact_id = await uc.submit(FORM, "1.2.3.4", None)
        assert [c.id for c in await uc.list(ContactStatus.NEW)] == [contact_id]
        await uc.set_status(contact_id, ContactStatus.ARCHIVED)
        assert await uc.list(ContactStatus.NEW) == []
        assert (await uc.get(contact_id)).status is ContactStatus.ARCHIVED
        await uc.delete(contact_id)
        for action in (uc.get, uc.delete):
            with pytest.raises(ContactNotFoundError):
                await action(contact_id)
        with pytest.raises(ContactNotFoundError):
            await uc.set_status(contact_id, ContactStatus.READ)

    async def test_purge_after_twelve_months(
        self, uc: ContactsUseCases, store: ContactsStore, clock: FixedClock
    ) -> None:
        old = await uc.submit(FORM, "1.1.1.1", None)
        clock.advance(timedelta(days=200))
        recent = await uc.submit(FORM, "2.2.2.2", None)
        clock.advance(timedelta(days=166))
        assert await uc.purge_expired() == "deleted 1 expired contacts"
        assert set(store.data) == {recent}
        assert old not in store.data


@pytest.fixture
def world() -> World:
    return make_world()


@pytest.fixture
async def client(world: World) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(world.app()), base_url="https://a.t") as c:
        yield c


BODY = {
    "from": "Ana",
    "contact": "ana@corp.dev",
    "brief": "AI Engineer role, remote.",
    "lang": "pt",
}


class TestHttp:
    async def test_public_submit(self, client: AsyncClient, world: World) -> None:
        response = await client.post("/api/contact", json=BODY, headers={"Idempotency-Key": "k1"})
        assert response.status_code == 202
        again = await client.post("/api/contact", json=BODY, headers={"Idempotency-Key": "k1"})
        assert again.json() == response.json()
        [stored] = world.contacts.data.values()
        assert (stored.form.name, stored.form.lang) == ("Ana", "pt")

    async def test_public_errors(self, client: AsyncClient) -> None:
        assert (
            await client.post("/api/contact", json={**BODY, "brief": "short"})
        ).status_code == 422
        for _ in range(5):
            await client.post("/api/contact", json=BODY)
        assert (await client.post("/api/contact", json=BODY)).status_code == 429

    async def test_admin_inbox(self, client: AsyncClient, world: World) -> None:
        contact_id = (await client.post("/api/contact", json=BODY)).json()["id"]
        await login(client, world)
        [listed] = (await client.get("/admin/contacts?status=new")).json()
        assert listed["contact"] == "ana@corp.dev"
        url = f"/admin/contacts/{contact_id}"
        assert (await client.patch(url, json={"status": "read"})).json()["status"] == "read"
        assert (await client.get(url)).json()["status"] == "read"
        assert (await client.delete(url)).status_code == 204
        assert (await client.get(url)).status_code == 404


async def test_resend_mailer_posts_plain_text() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200 if len(requests) == 1 else 500, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        mailer = ResendMailer(http, "re_key", "Erick <hi@erick.dev>")
        await mailer.send(OutgoingEmail("a@b.co", "Hi", "text", reply_to="c@d.co"))
        with pytest.raises(httpx.HTTPStatusError):
            await mailer.send(OutgoingEmail("a@b.co", "Hi", "text"))
    first, second = requests
    assert str(first.url) == RESEND_URL
    assert first.headers["authorization"] == "Bearer re_key"
    assert json.loads(first.content) == {
        "from": "Erick <hi@erick.dev>",
        "to": ["a@b.co"],
        "subject": "Hi",
        "text": "text",
        "reply_to": "c@d.co",
    }
    assert "reply_to" not in json.loads(second.content)
