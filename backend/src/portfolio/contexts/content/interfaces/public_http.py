"""The public, read-only API over published content (docs/public-api.md)."""

from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from portfolio.contexts.content.application.catalog import (
    AttachmentView,
    Availability,
    PublicCatalog,
    PublicEntry,
    PublicSkill,
)
from portfolio.contexts.content.domain.errors import NoSuchEntryError
from portfolio.contexts.content.domain.kinds import Kind, Lang
from portfolio.contexts.content.interfaces.documents import (
    SiteLinks,
    agents_md,
    json_resume,
    llms_txt,
)


def _catalog(request: Request) -> PublicCatalog:
    return cast(PublicCatalog, request.app.state.catalog)


def _links(request: Request) -> SiteLinks:
    return cast(SiteLinks, request.app.state.links)


Catalog = Annotated[PublicCatalog, Depends(_catalog)]
Links = Annotated[SiteLinks, Depends(_links)]
LangQuery = Annotated[Lang, Query(description="Language of the text fields")]

router = APIRouter(prefix="/api", tags=["portfolio"])
documents_router = APIRouter(tags=["portfolio"])


class LinkOut(BaseModel):
    label: str
    url: str


class AttachmentOut(BaseModel):
    label: str
    filename: str
    url: str
    content_type: str
    size: int

    @classmethod
    def of(cls, view: AttachmentView) -> "AttachmentOut":
        f = view.file
        return cls(
            label=view.label,
            filename=f.filename,
            url=f.url,
            content_type=f.content_type,
            size=f.size,
        )


class SkillRefOut(BaseModel):
    slug: str
    title: str


class EntryOut(BaseModel):
    kind: Kind
    slug: str
    title: str
    summary: str
    tags: list[str]
    details: dict[str, Any]
    body_html: str
    body: list[dict[str, Any]] = Field(
        description=(
            "The body in order: `html` runs (safe, rendered by the server) and structured "
            "`block`s (gallery, diagram, logos, metrics, timeline…) for the site to render"
        )
    )
    skills: list[SkillRefOut]
    attachments: list[AttachmentOut]
    published_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, entry: PublicEntry) -> "EntryOut":
        return cls(
            kind=entry.kind,
            slug=entry.slug,
            title=entry.title,
            summary=entry.summary,
            tags=list(entry.tags),
            details=dict(entry.details),
            body_html=entry.body_html,
            body=[dict(segment) for segment in entry.body],
            skills=[SkillRefOut(slug=s.slug, title=s.title) for s in entry.skills],
            attachments=[AttachmentOut.of(a) for a in entry.attachments],
            published_at=entry.published_at,
            updated_at=entry.updated_at,
        )


class AvailabilityOut(BaseModel):
    status: Literal["open", "not_looking", "unknown"]
    open: bool
    updated_at: str | None

    @classmethod
    def of(cls, availability: Availability) -> "AvailabilityOut":
        return cls(
            status=availability.status, open=availability.open, updated_at=availability.updated_at
        )


class ProfileOut(BaseModel):
    name: str
    headline: str
    summary: str
    bio_html: str
    location: str | None
    email: str | None
    links: list[LinkOut]
    availability: AvailabilityOut
    attachments: list[AttachmentOut]


class EvidenceOut(BaseModel):
    kind: Kind
    slug: str
    title: str


class SkillOut(BaseModel):
    slug: str
    title: str
    category: str
    evidence: list[EvidenceOut]
    services: list[str] = Field(
        default_factory=list, description="A cloud provider's services Erick has used"
    )

    @classmethod
    def of(cls, skill: PublicSkill) -> "SkillOut":
        return cls(
            slug=skill.slug,
            title=skill.title,
            category=skill.category,
            evidence=[EvidenceOut(kind=e.kind, slug=e.slug, title=e.title) for e in skill.evidence],
            services=list(skill.services),
        )


class NotFound(BaseModel):
    detail: str


@router.get("/profile", responses={404: {"model": NotFound}})
async def profile(catalog: Catalog, lang: LangQuery = Lang.EN) -> ProfileOut:
    """Who Erick is: headline, bio, links, availability and the CV download."""
    found = await catalog.profile(lang)
    if found is None:
        raise NoSuchEntryError("profile", "profile")
    return ProfileOut(
        name=found.name,
        headline=found.headline,
        summary=found.summary,
        bio_html=found.bio_html,
        location=found.location,
        email=found.email,
        links=[LinkOut(label=link["label"], url=link["url"]) for link in found.links],
        availability=AvailabilityOut.of(found.availability),
        attachments=[AttachmentOut.of(a) for a in found.attachments],
    )


@router.get("/availability")
async def availability(catalog: Catalog) -> AvailabilityOut:
    """Whether Erick is open to new work, and when that was last updated."""
    return AvailabilityOut.of(await catalog.availability())


@router.get("/projects")
async def projects(
    catalog: Catalog,
    lang: LangQuery = Lang.EN,
    collection: Literal["portfolio", "lab"] | None = None,
) -> list[EntryOut]:
    """Published case studies. `portfolio` is shipped work, `lab` is experiments."""
    return [EntryOut.of(e) for e in await catalog.entries(Kind.PROJECT, lang, collection)]


@router.get("/projects/{slug}", responses={404: {"model": NotFound}})
async def project(slug: str, catalog: Catalog, lang: LangQuery = Lang.EN) -> EntryOut:
    """One case study: the problem, the decisions, the result and the links that back it."""
    return EntryOut.of(await catalog.entry(Kind.PROJECT, slug, lang))


def _list_route(path: str, kind: Kind, summary: str) -> None:
    async def list_entries(catalog: Catalog, lang: LangQuery = Lang.EN) -> list[EntryOut]:
        return [EntryOut.of(e) for e in await catalog.entries(kind, lang)]

    router.add_api_route(path, list_entries, methods=["GET"], summary=summary, name=f"list_{kind}")


_list_route("/experience", Kind.EXPERIENCE, "Jobs, with role, dates and what was built")
_list_route("/education", Kind.EDUCATION, "Degrees and courses in progress")
_list_route("/certificates", Kind.CERTIFICATE, "Certificates")
_list_route("/studies", Kind.STUDY, "What Erick is reading and studying")
_list_route("/writing", Kind.WRITING, "Studies and articles written by Erick")


@router.get("/writing/{slug}", responses={404: {"model": NotFound}})
async def writing(slug: str, catalog: Catalog, lang: LangQuery = Lang.EN) -> EntryOut:
    return EntryOut.of(await catalog.entry(Kind.WRITING, slug, lang))


@router.get("/skills")
async def skills(catalog: Catalog, lang: LangQuery = Lang.EN) -> list[SkillOut]:
    """Each skill with the experiences and projects where it was actually used."""
    return [SkillOut.of(s) for s in await catalog.skills(lang)]


@router.get("/resume.json")
async def resume(catalog: Catalog, links: Links, lang: LangQuery = Lang.EN) -> dict[str, Any]:
    """The CV in the JSON Resume format (jsonresume.org)."""
    return json_resume(
        await catalog.profile(lang),
        work=await catalog.entries(Kind.EXPERIENCE, lang),
        education=await catalog.entries(Kind.EDUCATION, lang),
        certificates=await catalog.entries(Kind.CERTIFICATE, lang),
        projects=await catalog.entries(Kind.PROJECT, lang, "portfolio"),
        skills=await catalog.skills(lang),
        links=links,
    )


@documents_router.get("/AGENTS.md", response_class=PlainTextResponse)
async def agents(catalog: Catalog, links: Links) -> PlainTextResponse:
    """A brief for AI agents: who Erick is, availability, and how to contact him."""
    text = agents_md(
        await catalog.profile(Lang.EN),
        await catalog.availability(),
        await catalog.skills(Lang.EN),
        links,
    )
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@documents_router.get("/llms.txt", response_class=PlainTextResponse)
async def llms(catalog: Catalog, links: Links) -> PlainTextResponse:
    text = llms_txt(
        await catalog.profile(Lang.EN),
        await catalog.availability(),
        await catalog.entries(Kind.PROJECT, Lang.EN),
        links,
    )
    return PlainTextResponse(text)
