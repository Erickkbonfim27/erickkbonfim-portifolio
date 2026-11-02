"""Contact requests sent through the site or by a visitor's AI agent."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from portfolio.kernel.email import Email, InvalidEmailError

Lang = Literal["en", "pt"]

# LGPD: contact data is kept only long enough to answer, then deleted by a daily job.
RETENTION = timedelta(days=365)

MAX_NAME = 120
MIN_CONTACT = 3
MAX_CONTACT = 200
MIN_BRIEF = 10
MAX_BRIEF = 4000
MAX_COMPANY = 120
MAX_IDEMPOTENCY_KEY = 100


class ContactsError(Exception):
    pass


class InvalidContactError(ContactsError):
    pass


class ContactNotFoundError(ContactsError):
    def __init__(self, contact_id: UUID) -> None:
        super().__init__(f"contact {contact_id} not found")


class TooManyRequestsError(ContactsError):
    pass


class DuplicateSubmissionError(ContactsError):
    """The idempotency key was already used (a client retried)."""


class ContactStatus(StrEnum):
    NEW = "new"
    READ = "read"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ContactForm:
    name: str
    contact: str
    brief: str
    company: str | None
    lang: Lang

    @classmethod
    def build(
        cls, name: str, contact: str, brief: str, company: str | None, lang: Lang
    ) -> "ContactForm":
        name, contact, brief = name.strip(), contact.strip(), brief.strip()
        company = (company or "").strip() or None
        if not 1 <= len(name) <= MAX_NAME:
            raise InvalidContactError(f"from needs 1 to {MAX_NAME} characters")
        if not MIN_CONTACT <= len(contact) <= MAX_CONTACT:
            raise InvalidContactError(f"contact needs {MIN_CONTACT} to {MAX_CONTACT} characters")
        if not MIN_BRIEF <= len(brief) <= MAX_BRIEF:
            raise InvalidContactError(f"brief needs {MIN_BRIEF} to {MAX_BRIEF} characters")
        if company is not None and len(company) > MAX_COMPANY:
            raise InvalidContactError(f"company needs at most {MAX_COMPANY} characters")
        return cls(name, contact, brief, company, lang)


@dataclass(frozen=True, slots=True)
class ContactRequest:
    id: UUID
    form: ContactForm
    status: ContactStatus
    idempotency_key: str | None
    created_at: datetime
    notified_at: datetime | None = None
    thanked_at: datetime | None = None

    def reply_email(self) -> Email | None:
        """The address to thank, when the contact left an email (not a phone number)."""
        try:
            return Email.parse(self.form.contact)
        except InvalidEmailError:
            return None

    def with_status(self, status: ContactStatus) -> "ContactRequest":
        return replace(self, status=status)

    def notified(self, now: datetime) -> "ContactRequest":
        return replace(self, notified_at=now)

    def thanked(self, now: datetime) -> "ContactRequest":
        return replace(self, thanked_at=now)


def retention_cutoff(now: datetime) -> datetime:
    return now - RETENTION


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    reply_to: str | None = None


def owner_notification(owner: str, request: ContactRequest) -> OutgoingEmail:
    form = request.form
    lines = [
        f"From: {form.name}",
        f"Contact: {form.contact}",
        f"Company: {form.company or '-'}",
        f"Language: {form.lang}",
        f"Received: {request.created_at.isoformat()}",
        "",
        form.brief,
    ]
    reply = request.reply_email()
    return OutgoingEmail(
        to=owner,
        subject=f"New contact: {form.name}"[:150],
        text="\n".join(lines),
        reply_to=reply.value if reply else None,
    )


_THANK_YOU: dict[Lang, tuple[str, str]] = {
    "en": (
        "Thanks for reaching out",
        "Hi,\n\nThanks for getting in touch. Erick received your message and will reply "
        "to this address soon.\n\nErick Kopak Bonfim",
    ),
    "pt": (
        "Obrigado pelo contato",
        "Olá,\n\nObrigado pelo contato. O Erick recebeu sua mensagem e vai responder "
        "neste endereço em breve.\n\nErick Kopak Bonfim",
    ),
}


def thank_you(to: Email, lang: Lang) -> OutgoingEmail:
    """A fixed template: nothing the visitor typed is echoed back, so the form cannot
    be used to send someone else arbitrary text from this domain."""
    subject, text = _THANK_YOU[lang]
    return OutgoingEmail(to=to.value, subject=subject, text=text)
