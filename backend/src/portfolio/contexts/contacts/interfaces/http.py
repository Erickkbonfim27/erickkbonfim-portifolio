from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from portfolio.contexts.contacts.application.use_cases import ContactsUseCases
from portfolio.contexts.contacts.domain.model import (
    MAX_BRIEF,
    MAX_COMPANY,
    MAX_CONTACT,
    MAX_IDEMPOTENCY_KEY,
    MAX_NAME,
    ContactForm,
    ContactNotFoundError,
    ContactRequest,
    ContactStatus,
    TooManyRequestsError,
)


def _use_cases(request: Request) -> ContactsUseCases:
    return cast(ContactsUseCases, request.app.state.contacts)


UseCases = Annotated[ContactsUseCases, Depends(_use_cases)]


# --- public -------------------------------------------------------------------

public_router = APIRouter(prefix="/api", tags=["contact"])


class ContactIn(BaseModel):
    """What a visitor, or a visitor's AI agent, sends to start a conversation."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", max_length=MAX_NAME, description="Who is writing")
    contact: str = Field(max_length=MAX_CONTACT, description="Email or phone to reply to")
    brief: str = Field(max_length=MAX_BRIEF, description="The opportunity, in a few lines")
    company: str | None = Field(default=None, max_length=MAX_COMPANY)
    lang: Literal["en", "pt"] = "en"
    # Honeypot: hidden in the site's form. Humans leave it empty; naive bots fill it.
    website: str = Field(default="", max_length=200, exclude=True)


class Accepted(BaseModel):
    id: UUID


@public_router.post("/contact", status_code=status.HTTP_202_ACCEPTED)
async def submit_contact(
    body: ContactIn,
    request: Request,
    use_cases: UseCases,
    idempotency_key: Annotated[
        str | None, Header(max_length=MAX_IDEMPOTENCY_KEY, description="Retry-safe key")
    ] = None,
) -> Accepted:
    """Send Erick a message about a job opportunity. The reply goes to `contact`.
    Contact data is used only to answer and is deleted after 12 months."""
    form = ContactForm.build(body.from_, body.contact, body.brief, body.company, body.lang)
    client = request.client.host if request.client else "unknown"
    contact_id = await use_cases.submit(form, client, idempotency_key, honeypot=body.website)
    return Accepted(id=contact_id)


# --- admin --------------------------------------------------------------------

admin_router = APIRouter(prefix="/admin/contacts", include_in_schema=False)


class ContactOut(BaseModel):
    id: UUID
    name: str
    contact: str
    brief: str
    company: str | None
    lang: str
    status: ContactStatus
    created_at: datetime
    notified_at: datetime | None
    thanked_at: datetime | None

    @classmethod
    def of(cls, request: ContactRequest) -> "ContactOut":
        form = request.form
        return cls(
            id=request.id,
            name=form.name,
            contact=form.contact,
            brief=form.brief,
            company=form.company,
            lang=form.lang,
            status=request.status,
            created_at=request.created_at,
            notified_at=request.notified_at,
            thanked_at=request.thanked_at,
        )


class StatusIn(BaseModel):
    status: ContactStatus


@admin_router.get("")
async def list_contacts(
    use_cases: UseCases, status: ContactStatus | None = None
) -> list[ContactOut]:
    return [ContactOut.of(r) for r in await use_cases.list(status)]


@admin_router.get("/{contact_id}")
async def get_contact(contact_id: UUID, use_cases: UseCases) -> ContactOut:
    return ContactOut.of(await use_cases.get(contact_id))


@admin_router.patch("/{contact_id}")
async def set_status(contact_id: UUID, body: StatusIn, use_cases: UseCases) -> ContactOut:
    return ContactOut.of(await use_cases.set_status(contact_id, body.status))


@admin_router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: UUID, use_cases: UseCases) -> None:
    await use_cases.delete(contact_id)


def error_response(_: Request, error: Exception) -> JSONResponse:
    """Maps domain errors to HTTP. Registered on the app for ContactsError."""
    code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if isinstance(error, ContactNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, TooManyRequestsError):
        code = status.HTTP_429_TOO_MANY_REQUESTS
    return JSONResponse({"detail": str(error)}, status_code=code)
