"""Admin API for content. Mounted behind the admin session in `main.py`."""

from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from portfolio.contexts.content.application.use_cases import ContentUseCases
from portfolio.contexts.content.domain.details import SCHEMAS
from portfolio.contexts.content.domain.entry import (
    MAX_SUMMARY,
    MAX_TITLE,
    Attachment,
    Entry,
    EntryDraft,
    Translation,
)
from portfolio.contexts.content.domain.errors import (
    EntryNotFoundError,
    NoSuchEntryError,
    SingletonKindError,
    SlugTakenError,
    VersionConflictError,
)
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status


def _use_cases(request: Request) -> ContentUseCases:
    return cast(ContentUseCases, request.app.state.content)


UseCases = Annotated[ContentUseCases, Depends(_use_cases)]

router = APIRouter(prefix="/admin/content", include_in_schema=False)


class TranslationIn(BaseModel):
    title: str = Field(max_length=MAX_TITLE)
    summary: str = Field(default="", max_length=MAX_SUMMARY)
    body: dict[str, Any] | None = None


class AttachmentIn(BaseModel):
    file_id: UUID
    label: str


class EntryIn(BaseModel):
    slug: str
    translations: dict[Lang, TranslationIn]
    details: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    skills: list[UUID] = Field(default_factory=list)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    position: int = 0

    def to_draft(self, kind: Kind) -> EntryDraft:
        return EntryDraft.build(
            kind,
            slug=self.slug,
            translations={
                lang: Translation.create(t.title, t.summary, t.body)
                for lang, t in self.translations.items()
            },
            details=self.details,
            tags=self.tags,
            skills=self.skills,
            attachments=[Attachment(a.file_id, a.label) for a in self.attachments],
            position=self.position,
        )


class CreateEntryIn(EntryIn):
    kind: Kind


class UpdateEntryIn(EntryIn):
    version: int


class VersionIn(BaseModel):
    version: int


class TranslationOut(BaseModel):
    title: str
    summary: str
    body: dict[str, Any]


class AttachmentOut(BaseModel):
    file_id: UUID
    label: str


class EntryOut(BaseModel):
    id: UUID
    kind: Kind
    status: Status
    version: int
    slug: str
    translations: dict[Lang, TranslationOut]
    details: dict[str, Any]
    tags: list[str]
    skills: list[UUID]
    attachments: list[AttachmentOut]
    position: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None

    @classmethod
    def of(cls, entry: Entry) -> "EntryOut":
        content = entry.content
        return cls(
            id=entry.id,
            kind=entry.kind,
            status=entry.status,
            version=entry.version,
            slug=content.slug,
            translations={
                lang: TranslationOut(title=t.title, summary=t.summary, body=dict(t.body))
                for lang, t in content.translations.items()
            },
            details=dict(content.details),
            tags=list(content.tags),
            skills=list(content.skills),
            attachments=[
                AttachmentOut(file_id=a.file_id, label=a.label) for a in content.attachments
            ],
            position=content.position,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            published_at=entry.published_at,
        )


class FieldOut(BaseModel):
    name: str
    type: str
    required: bool
    choices: list[str]


@router.get("/kinds")
async def kinds() -> dict[Kind, list[FieldOut]]:
    """The structured fields of each kind, so the admin form is generated, not hard-coded."""
    return {
        kind: [
            FieldOut(name=f.name, type=f.type, required=f.required, choices=list(f.choices))
            for f in fields
        ]
        for kind, fields in SCHEMAS.items()
    }


@router.get("/entries")
async def list_entries(
    use_cases: UseCases, kind: Kind | None = None, status: Status | None = None
) -> list[EntryOut]:
    return [EntryOut.of(entry) for entry in await use_cases.list(kind, status)]


@router.post("/entries", status_code=status.HTTP_201_CREATED)
async def create_entry(body: CreateEntryIn, use_cases: UseCases) -> EntryOut:
    return EntryOut.of(await use_cases.create(body.kind, body.to_draft(body.kind)))


@router.get("/entries/{entry_id}")
async def get_entry(entry_id: UUID, use_cases: UseCases) -> EntryOut:
    return EntryOut.of(await use_cases.get(entry_id))


@router.put("/entries/{entry_id}")
async def update_entry(entry_id: UUID, body: UpdateEntryIn, use_cases: UseCases) -> EntryOut:
    current = await use_cases.get(entry_id)
    draft = body.to_draft(current.kind)
    return EntryOut.of(await use_cases.update(entry_id, body.version, draft))


@router.post("/entries/{entry_id}/publish")
async def publish_entry(entry_id: UUID, body: VersionIn, use_cases: UseCases) -> EntryOut:
    return EntryOut.of(await use_cases.publish(entry_id, body.version))


@router.post("/entries/{entry_id}/unpublish")
async def unpublish_entry(entry_id: UUID, body: VersionIn, use_cases: UseCases) -> EntryOut:
    return EntryOut.of(await use_cases.unpublish(entry_id, body.version))


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: UUID, use_cases: UseCases) -> None:
    await use_cases.delete(entry_id)


def error_response(_: Request, error: Exception) -> JSONResponse:
    """Maps domain errors to HTTP. Registered on the app for ContentError."""
    code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if isinstance(error, EntryNotFoundError | NoSuchEntryError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, SlugTakenError | SingletonKindError | VersionConflictError):
        code = status.HTTP_409_CONFLICT
    body: dict[str, Any] = {"detail": str(error)}
    if isinstance(error, VersionConflictError):
        body["current_version"] = error.current
    return JSONResponse(body, status_code=code)
