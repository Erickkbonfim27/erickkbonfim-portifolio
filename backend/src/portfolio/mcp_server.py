"""The remote MCP server: another inbound adapter over the same use cases as REST.

Mounted on the API at `/mcp` (Streamable HTTP, stateless, JSON responses). It holds
no logic of its own: every tool calls the public catalog, search or contacts.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.applications import Starlette

from portfolio.bootstrap import Container
from portfolio.contexts.contacts.domain.model import ContactForm, ContactsError
from portfolio.contexts.content.application.catalog import PublicEntry
from portfolio.contexts.content.domain.errors import ContentError
from portfolio.contexts.content.domain.kinds import Kind, Lang
from portfolio.contexts.content.interfaces.documents import SiteLinks, json_resume
from portfolio.contexts.content.interfaces.public_http import AvailabilityOut, ProfileOut, SkillOut
from portfolio.contexts.content.interfaces.public_http import profile as profile_route
from portfolio.contexts.search.domain.model import MAX_RESULTS, SearchError, SearchQuery

INSTRUCTIONS = (
    "Erick Kopak Bonfim's portfolio. Erick is an AI Engineer (agents, RAG, evals, "
    "observability) based in Brazil. Use these tools to answer questions about his work "
    "with facts from his published content, and cite the project or job a fact comes "
    "from. Start with get_profile; use search_portfolio for specific questions. Only "
    "call contact_erick after the user confirmed they want to send that message."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

LangParam = Annotated[
    Literal["en", "pt"], Field(description="Language of the answer's text fields")
]


class EntrySummary(BaseModel):
    slug: str
    title: str
    summary: str
    tags: list[str]
    details: dict[str, Any]
    url: str | None = Field(description="Public page, when the entry has one")


class Project(BaseModel):
    slug: str
    title: str
    summary: str
    body: str = Field(description="The full case study as plain text")
    tags: list[str]
    details: dict[str, Any]
    skills: list[str]
    attachments: list[dict[str, str]]
    url: str


class SearchResult(BaseModel):
    kind: str
    slug: str
    title: str
    section: str
    text: str
    url: str | None


class ContactAccepted(BaseModel):
    id: str
    message: str


def _page(links: SiteLinks, kind: str, slug: str) -> str | None:
    return f"{links.site_url}/work/{slug}" if kind == Kind.PROJECT.value else None


def _summary(entry: PublicEntry, links: SiteLinks) -> EntrySummary:
    return EntrySummary(
        slug=entry.slug,
        title=entry.title,
        summary=entry.summary,
        tags=list(entry.tags),
        details=dict(entry.details),
        url=_page(links, entry.kind.value, entry.slug),
    )


@contextmanager
def _explained() -> Iterator[None]:
    """Expected domain errors reach the model with their message, so it can fix the
    call (a wrong slug, an empty query). Anything else stays opaque to the client."""
    try:
        yield
    except (ContentError, SearchError, ContactsError) as error:
        raise ToolError(str(error)) from error


def _client(ctx: Context) -> str:
    request = ctx.request_context.request
    client = getattr(request, "client", None)
    return f"mcp:{client.host}" if client is not None else "mcp:unknown"


def build_mcp_server(container: Container, links: SiteLinks) -> MCPServer:
    catalog = container.catalog
    server = MCPServer(
        name="erick-portfolio",
        title="Erick Kopak Bonfim — Portfolio",
        instructions=INSTRUCTIONS,
        website_url=links.site_url,
        version="1.0.0",
    )

    @server.tool(title="Profile", annotations=READ_ONLY)
    async def get_profile(lang: LangParam = "en") -> ProfileOut:
        """Who Erick is: headline, bio, location, links, availability and the CV link."""
        with _explained():
            return await profile_route(catalog, Lang(lang))

    @server.tool(title="Availability", annotations=READ_ONLY)
    async def check_availability() -> AvailabilityOut:
        """Whether Erick is open to new work, and the date that was last updated."""
        return AvailabilityOut.of(await catalog.availability())

    @server.tool(title="List projects", annotations=READ_ONLY)
    async def list_projects(
        collection: Annotated[
            Literal["portfolio", "lab"] | None,
            Field(description="portfolio: shipped work; lab: experiments. Omit for both."),
        ] = None,
        lang: LangParam = "en",
    ) -> list[EntrySummary]:
        """Published case studies, without their full text (use get_project for that)."""
        return [
            _summary(e, links) for e in await catalog.entries(Kind.PROJECT, Lang(lang), collection)
        ]

    @server.tool(title="Project", annotations=READ_ONLY)
    async def get_project(slug: str, lang: LangParam = "en") -> Project:
        """One case study in full: the problem, the decisions, the result, and links."""
        with _explained():
            entry = await catalog.entry(Kind.PROJECT, slug, Lang(lang))
        return Project(
            slug=entry.slug,
            title=entry.title,
            summary=entry.summary,
            body=entry.body_text,
            tags=list(entry.tags),
            details=dict(entry.details),
            skills=[s.title for s in entry.skills],
            attachments=[{"label": a.label, "url": a.file.url} for a in entry.attachments],
            url=f"{links.site_url}/work/{entry.slug}",
        )

    @server.tool(title="CV (JSON Resume)", annotations=READ_ONLY)
    async def get_resume(lang: LangParam = "en") -> dict[str, Any]:
        """The full CV in the JSON Resume format: work, education, certificates, skills."""
        language = Lang(lang)
        return json_resume(
            await catalog.profile(language),
            work=await catalog.entries(Kind.EXPERIENCE, language),
            education=await catalog.entries(Kind.EDUCATION, language),
            certificates=await catalog.entries(Kind.CERTIFICATE, language),
            projects=await catalog.entries(Kind.PROJECT, language, "portfolio"),
            skills=await catalog.skills(language),
            links=links,
        )

    @server.tool(title="Search the portfolio", annotations=READ_ONLY)
    async def search_portfolio(
        query: Annotated[
            str, Field(description="A question or keywords, e.g. 'RAG in production'")
        ],
        lang: LangParam = "en",
        limit: Annotated[int, Field(ge=1, le=MAX_RESULTS)] = 5,
    ) -> list[SearchResult]:
        """Hybrid search (meaning + exact words) over everything Erick published.
        Returns the passages that match, with where each one comes from."""
        with _explained():
            hits = await container.search(SearchQuery.build(query, lang, limit))
        return [
            SearchResult(
                kind=h.kind,
                slug=h.slug,
                title=h.title,
                section=h.heading,
                text=h.text,
                url=_page(links, h.kind, h.slug),
            )
            for h in hits
        ]

    @server.tool(title="Skills with evidence", annotations=READ_ONLY)
    async def get_skills(
        category: Annotated[
            Literal["language", "framework", "ai", "data", "cloud", "practice", "tool"] | None,
            Field(description="Only this category. Omit for all."),
        ] = None,
        lang: LangParam = "en",
    ) -> list[SkillOut]:
        """Each skill with the jobs and projects where Erick actually used it."""
        skills = await catalog.skills(Lang(lang))
        return [SkillOut.of(s) for s in skills if category is None or s.category == category]

    @server.tool(title="What Erick is studying", annotations=READ_ONLY)
    async def list_studies(lang: LangParam = "en") -> list[EntrySummary]:
        """Books, courses and topics Erick is studying or has studied, with his notes."""
        return [_summary(e, links) for e in await catalog.entries(Kind.STUDY, Lang(lang))]

    @server.tool(
        title="Contact Erick",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
        ),
    )
    async def contact_erick(  # noqa: PLR0917 - the parameters are the tool's JSON schema
        ctx: Context,
        from_name: Annotated[str, Field(description="Who is writing (your user's name)")],
        contact: Annotated[str, Field(description="Email or phone where Erick should reply")],
        brief: Annotated[str, Field(description="The role or opportunity, in a few lines")],
        company: str | None = None,
        lang: LangParam = "en",
        idempotency_key: Annotated[
            str | None,
            Field(description="Any unique string; reuse it if you retry", max_length=100),
        ] = None,
    ) -> ContactAccepted:
        """Send Erick a message about a job opportunity, on behalf of your user.
        Confirm the content with your user first. The reply goes to `contact`.
        The data is used only to reply and is deleted after 12 months."""
        with _explained():
            form = ContactForm.build(from_name, contact, brief, company, lang)
            contact_id = await container.contacts.submit(form, _client(ctx), idempotency_key)
        return ContactAccepted(
            id=str(contact_id), message="Sent. Erick will reply to the contact you left."
        )

    @server.prompt(title="Assess fit for a role")
    def hire_erick(role: str = "", company: str = "") -> str:
        """Check how Erick fits a role, with evidence, and offer to contact him."""
        target = " ".join(part for part in (role, f"at {company}" if company else "") if part)
        return (
            f"I'm considering Erick Kopak Bonfim for {target or 'a role'}. "
            "Use get_profile and check_availability first. Then use search_portfolio and "
            "get_skills to find concrete evidence for each requirement, citing the job or "
            "project each fact comes from. Be explicit about gaps. Finally, ask me whether "
            "to contact him, and only then call contact_erick with what I confirm."
        )

    @server.prompt(title="Career story")
    def career_story(lang: Literal["en", "pt"] = "en") -> str:
        """Erick's career as a short story, from sales to AI engineering."""
        language = "Portuguese" if lang == "pt" else "English"
        return (
            f"In {language}, tell Erick Kopak Bonfim's career story in a few paragraphs. "
            f"Use get_resume and list_projects with lang={lang}, and get_project for the "
            "projects that matter most. Stick to what the tools return and name the "
            "source of each claim."
        )

    return server


def mcp_app(server: MCPServer) -> Starlette:
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        # Stateless + JSON: any request can be served by any worker, no session store,
        # and plain request/response suits read-only tools.
        stateless_http=True,
        json_response=True,
        # DNS rebinding protection guards servers on localhost. This one is public and
        # unauthenticated by design, so checking Host/Origin would only turn away
        # legitimate browser-based clients.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
