"""The public read side: catalog, generated documents and the public HTTP API."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from portfolio.bootstrap import Container
from portfolio.contexts.content.application.catalog import Availability, PublicEntry, PublicProfile
from portfolio.contexts.content.domain.entry import Attachment, Entry, EntryDraft, Translation
from portfolio.contexts.content.domain.errors import NoSuchEntryError
from portfolio.contexts.content.domain.kinds import Kind, Lang
from portfolio.contexts.content.interfaces.documents import (
    SiteLinks,
    agents_md,
    json_resume,
    llms_txt,
)
from tests.unit.files.test_files import PDF
from tests.unit.support import World, make_world

LINKS = SiteLinks("https://erick.test", "https://api.erick.test")
BODY = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<b>bold</b>"}]}],
}


def texts(en: str, pt: str, summary: str = "s", body: object = None) -> dict[Lang, Translation]:
    return {
        Lang.EN: Translation.create(en, summary, body),
        Lang.PT: Translation.create(pt, f"{summary}-pt", body),
    }


@dataclass
class Seeded:
    world: World
    container: Container
    python: Entry
    loopia: Entry
    vizzion: Entry


async def seed(world: World, *, with_profile: bool = True) -> Seeded:
    container = world.container()
    content = container.content

    async def publish(kind: Kind, **draft: Any) -> Entry:
        entry = await content.create(kind, EntryDraft.build(kind, **draft))
        return await content.publish(entry.id, entry.version)

    cv = (await container.files.upload("Erick CV.pdf", PDF)).file
    python = await publish(
        Kind.SKILL,
        slug="python",
        translations=texts("Python", "Python"),
        details={"category": "language"},
    )
    hidden_skill = await content.create(
        Kind.SKILL,
        EntryDraft.build(
            Kind.SKILL,
            slug="cobol",
            translations=texts("COBOL", "COBOL"),
            details={"category": "language"},
        ),
    )
    if with_profile:
        await publish(
            Kind.PROFILE,
            slug="erick",
            translations=texts("AI Engineer", "Engenheiro de IA", "Builds agents", BODY),
            details={
                "name": "Erick",
                "location": "Brusque, SC",
                "email": "erick@x.dev",
                "availability": "open",
                "links": [{"label": "GitHub", "url": "https://github.com/e"}],
            },
            attachments=[Attachment(cv.id, "CV")],
        )
    loopia = await publish(
        Kind.EXPERIENCE,
        slug="loopia",
        translations=texts("Software Engineer", "Engenheiro de software"),
        details={
            "organization": "Loopia",
            "start": "2026-05",
            "end": "2026-10",
            "url": "https://l.co",
        },
        skills=[python.id, hidden_skill.id],
    )
    await publish(
        Kind.EXPERIENCE,
        slug="silpi",
        translations=texts("Engineer", "Engenheiro"),
        details={"organization": "SILPI", "start": "2024-06"},
    )
    await content.create(  # a draft: never public
        Kind.EXPERIENCE,
        EntryDraft.build(
            Kind.EXPERIENCE,
            slug="secret",
            translations=texts("Secret", "Segredo"),
            details={"organization": "X", "start": "2026-11"},
        ),
    )
    vizzion = await publish(
        Kind.PROJECT,
        slug="vizzion",
        translations=texts("Vizzion", "Vizzion", "Urban AI", BODY),
        details={"collection": "portfolio", "start": "2024-03", "end": "2025-10"},
        tags=["GIS"],
        skills=[python.id],
        attachments=[Attachment(cv.id, "Deck")],
    )
    await publish(
        Kind.PROJECT,
        slug="prospecta",
        translations=texts("Prospecta", "Prospecta", "Lab"),
        details={"collection": "lab", "state": "standby"},
    )
    await publish(
        Kind.EDUCATION,
        slug="pucrs",
        translations=texts("Database technologist", "Tecnólogo em banco de dados"),
        details={"institution": "PUCRS", "start": "2026-04"},
    )
    await publish(
        Kind.CERTIFICATE,
        slug="langsmith",
        translations=texts("Building Reliable Agents", "Agentes confiáveis"),
        details={"issuer": "LangChain", "issued": "2026-10"},
    )
    return Seeded(world, container, python, loopia, vizzion)


@pytest.fixture
async def seeded() -> Seeded:
    return await seed(make_world())


class TestCatalog:
    async def test_lists_only_published_newest_first(self, seeded: Seeded) -> None:
        experience = await seeded.container.catalog.entries(Kind.EXPERIENCE, Lang.EN)
        assert [e.slug for e in experience] == ["loopia", "silpi"]

    async def test_position_wins_over_date(self, seeded: Seeded) -> None:
        content = seeded.container.content
        silpi = next(e for e in await content.list(Kind.EXPERIENCE) if e.slug == "silpi")
        draft = EntryDraft.build(
            Kind.EXPERIENCE,
            slug="silpi",
            translations=silpi.content.translations,
            details=silpi.content.details,
            position=-1,
        )
        await content.update(silpi.id, silpi.version, draft)
        experience = await seeded.container.catalog.entries(Kind.EXPERIENCE, Lang.EN)
        assert [e.slug for e in experience] == ["silpi", "loopia"]

    async def test_entry_view_in_each_language(self, seeded: Seeded) -> None:
        catalog = seeded.container.catalog
        en = await catalog.entry(Kind.EXPERIENCE, "loopia", Lang.EN)
        pt = await catalog.entry(Kind.EXPERIENCE, "loopia", Lang.PT)
        assert (en.title, pt.title) == ("Software Engineer", "Engenheiro de software")
        # The draft skill is not even named publicly.
        assert [s.slug for s in en.skills] == ["python"]

    async def test_body_is_rendered_and_attachments_resolved(self, seeded: Seeded) -> None:
        project = await seeded.container.catalog.entry(Kind.PROJECT, "vizzion", Lang.EN)
        assert project.body_html == "<p>&lt;b&gt;bold&lt;/b&gt;</p>"
        [deck] = project.attachments
        assert deck.label == "Deck"
        assert deck.file.filename == "Erick CV.pdf"
        assert deck.file.url.startswith("https://files.test/")

    async def test_collections(self, seeded: Seeded) -> None:
        catalog = seeded.container.catalog
        assert [p.slug for p in await catalog.entries(Kind.PROJECT, Lang.EN, "lab")] == [
            "prospecta"
        ]
        assert len(await catalog.entries(Kind.PROJECT, Lang.EN)) == 2

    async def test_drafts_and_unknown_slugs_are_not_found(self, seeded: Seeded) -> None:
        for slug in ("secret", "nope"):
            with pytest.raises(NoSuchEntryError):
                await seeded.container.catalog.entry(Kind.EXPERIENCE, slug, Lang.EN)

    async def test_skills_carry_evidence(self, seeded: Seeded) -> None:
        [python] = await seeded.container.catalog.skills(Lang.PT)
        assert (python.slug, python.category) == ("python", "language")
        assert [(e.kind, e.slug, e.title) for e in python.evidence] == [
            (Kind.EXPERIENCE, "loopia", "Engenheiro de software"),
            (Kind.PROJECT, "vizzion", "Vizzion"),
        ]

    async def test_a_provider_carries_its_services(self, seeded: Seeded) -> None:
        content = seeded.container.content
        draft = EntryDraft.build(
            Kind.SKILL,
            slug="aws",
            translations=texts("AWS", "AWS"),
            details={"category": "cloud", "services": ["Lambda", "SQS"]},
        )
        aws = await content.create(Kind.SKILL, draft)
        await content.publish(aws.id, aws.version)
        skills = await seeded.container.catalog.skills(Lang.EN)
        assert {s.slug: s.services for s in skills} == {"python": (), "aws": ("Lambda", "SQS")}
        resume = json_resume(
            None, work=(), education=(), certificates=(), projects=(), skills=skills, links=LINKS
        )
        assert resume["skills"][-1] == {
            "name": "cloud",
            "keywords": ["AWS", "AWS Lambda", "AWS SQS"],
        }

    async def test_profile_and_availability(self, seeded: Seeded) -> None:
        catalog = seeded.container.catalog
        profile = await catalog.profile(Lang.EN)
        assert profile is not None
        assert (profile.name, profile.headline, profile.location) == (
            "Erick",
            "AI Engineer",
            "Brusque, SC",
        )
        assert profile.availability == Availability("open", "2026-11-02")
        assert [a.label for a in profile.attachments] == ["CV"]
        assert await catalog.availability() == Availability("open", "2026-11-02")

    async def test_no_profile_yet(self) -> None:
        seeded = await seed(make_world(), with_profile=False)
        assert await seeded.container.catalog.profile(Lang.EN) is None
        availability = await seeded.container.catalog.availability()
        assert (availability.status, availability.open) == ("unknown", False)


class TestDocuments:
    async def test_agents_md(self, seeded: Seeded) -> None:
        catalog = seeded.container.catalog
        text = agents_md(
            await catalog.profile(Lang.EN),
            await catalog.availability(),
            await catalog.skills(Lang.EN),
            LINKS,
        )
        assert text.startswith("# AGENTS.md: Erick\n\nAI Engineer. Based in Brusque, SC.")
        assert "Availability: open to new work (updated 2026-11-02)." in text
        assert "POST https://api.erick.test/api/contact" in text
        assert "Stack: Python." in text

    def test_agents_md_before_any_content(self) -> None:
        text = agents_md(None, Availability("unknown", None), [], LINKS)
        assert text.startswith("# AGENTS.md: this portfolio")
        assert "Availability: not published yet." in text
        assert "Stack:" not in text

    def test_not_looking(self) -> None:
        text = llms_txt(None, Availability("not_looking", None), [], LINKS)
        assert text.startswith("# Portfolio\n")
        assert "Availability: not looking right now." in text
        assert "## Projects" not in text

    async def test_llms_txt(self, seeded: Seeded) -> None:
        catalog = seeded.container.catalog
        text = llms_txt(
            await catalog.profile(Lang.EN),
            await catalog.availability(),
            await catalog.entries(Kind.PROJECT, Lang.EN),
            LINKS,
        )
        assert "> AI Engineer. Builds agents" in text
        assert "- [Vizzion](https://erick.test/work/vizzion): Urban AI" in text


@pytest.fixture
async def client(seeded: Seeded) -> AsyncIterator[AsyncClient]:
    app = seeded.world.app()
    async with AsyncClient(transport=ASGITransport(app), base_url="https://api.erick.test") as c:
        yield c


class TestHttp:
    async def test_profile(self, client: AsyncClient) -> None:
        response = await client.get("/api/profile?lang=pt")
        body = response.json()
        assert body["headline"] == "Engenheiro de IA"
        assert body["links"] == [{"label": "GitHub", "url": "https://github.com/e"}]
        assert body["availability"] == {"status": "open", "open": True, "updated_at": "2026-11-02"}
        assert body["attachments"][0]["label"] == "CV"
        assert response.headers["cache-control"].startswith("public, max-age=60")

    async def test_profile_404_before_publishing(self) -> None:
        world = make_world()
        async with AsyncClient(transport=ASGITransport(world.app()), base_url="https://a.t") as c:
            assert (await c.get("/api/profile")).status_code == 404
            assert (await c.get("/api/availability")).json()["status"] == "unknown"

    @pytest.mark.parametrize(
        ("path", "slugs"),
        [
            ("/api/projects", ["vizzion", "prospecta"]),
            ("/api/projects?collection=lab", ["prospecta"]),
            ("/api/experience", ["loopia", "silpi"]),
            ("/api/education", ["pucrs"]),
            ("/api/certificates", ["langsmith"]),
            ("/api/studies", []),
            ("/api/writing", []),
        ],
    )
    async def test_lists(self, client: AsyncClient, path: str, slugs: list[str]) -> None:
        assert [e["slug"] for e in (await client.get(path)).json()] == slugs

    async def test_project_detail(self, client: AsyncClient) -> None:
        body = (await client.get("/api/projects/vizzion")).json()
        assert body["body_html"].startswith("<p>")
        assert body["skills"] == [{"slug": "python", "title": "Python"}]
        assert set(body["attachments"][0]) == {"label", "filename", "url", "content_type", "size"}

    async def test_unknown_slugs(self, client: AsyncClient) -> None:
        assert (await client.get("/api/projects/nope")).status_code == 404
        assert (await client.get("/api/writing/nope")).status_code == 404
        assert (await client.get("/api/projects?collection=secret")).status_code == 422

    async def test_skills(self, client: AsyncClient) -> None:
        [python] = (await client.get("/api/skills")).json()
        assert [e["slug"] for e in python["evidence"]] == ["loopia", "vizzion"]
        assert python["services"] == []

    async def test_json_resume(self, client: AsyncClient) -> None:
        resume = (await client.get("/api/resume.json")).json()
        assert resume["basics"]["name"] == "Erick"
        assert resume["basics"]["location"] == {"city": "Brusque, SC"}
        assert resume["basics"]["profiles"] == [
            {"network": "GitHub", "url": "https://github.com/e"}
        ]
        assert resume["work"][0] == {
            "name": "Loopia",
            "position": "Software Engineer",
            "summary": "s",
            "url": "https://l.co",
            "startDate": "2026-05",
            "endDate": "2026-10",
        }
        assert resume["education"][0]["institution"] == "PUCRS"
        assert resume["certificates"][0] == {
            "name": "Building Reliable Agents",
            "issuer": "LangChain",
            "date": "2026-10",
        }
        assert [p["name"] for p in resume["projects"]] == ["Vizzion"]  # portfolio only
        assert resume["skills"] == [{"name": "language", "keywords": ["Python"]}]
        assert resume["meta"]["canonical"] == "https://api.erick.test/api/resume.json"

    async def test_json_resume_without_profile(self) -> None:
        world = make_world()
        async with AsyncClient(transport=ASGITransport(world.app()), base_url="https://a.t") as c:
            resume = (await c.get("/api/resume.json")).json()
        assert resume["basics"] == {"url": "https://erick.test"}

    async def test_agent_documents(self, client: AsyncClient) -> None:
        agents = await client.get("/AGENTS.md")
        assert agents.headers["content-type"] == "text/markdown; charset=utf-8"
        assert agents.text.startswith("# AGENTS.md: Erick")
        llms = await client.get("/llms.txt")
        assert llms.headers["content-type"].startswith("text/plain")
        assert llms.headers["cache-control"].startswith("public")

    async def test_admin_is_never_cached_and_writes_are_not_cached(
        self, client: AsyncClient
    ) -> None:
        assert (await client.get("/admin/auth/me")).headers["cache-control"] == "no-store"
        contact = await client.post(
            "/api/contact", json={"from": "A", "contact": "a@b.co", "brief": "AI Engineer role"}
        )
        assert "cache-control" not in contact.headers


def test_json_resume_omits_what_the_profile_does_not_say() -> None:
    profile = PublicProfile(
        name="Erick",
        headline="AI Engineer",
        summary="",
        bio_html="",
        location=None,
        email=None,
        links=(),
        availability=Availability("open", None),
        attachments=(),
    )
    empty: list[PublicEntry] = []
    basics = json_resume(
        profile,
        work=empty,
        education=empty,
        certificates=empty,
        projects=empty,
        skills=[],
        links=LINKS,
    )["basics"]
    assert "email" not in basics
    assert "location" not in basics
    assert basics["profiles"] == []
