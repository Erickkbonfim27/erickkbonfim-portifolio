from collections.abc import AsyncIterator, Iterable
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from portfolio.contexts.content.domain import richtext
from portfolio.contexts.content.domain.entry import EntryDraft, Translation
from portfolio.contexts.content.domain.kinds import Kind, Lang
from portfolio.contexts.search.domain.model import (
    MAX_CHUNK_CHARS,
    InvalidQueryError,
    SearchQuery,
    Section,
    SourceDocument,
    chunk_document,
    chunk_id,
)
from portfolio.contexts.search.infrastructure.encoders import FastembedBm25, FastembedDense
from portfolio.contexts.search.interfaces import consumer
from portfolio.platform.messaging import Delivery
from tests.unit.content.test_public import seed
from tests.unit.support import World, make_world

H2 = {"type": "heading", "attrs": {"level": 2}}


def heading(text: str) -> dict[str, Any]:
    return {**H2, "content": [{"type": "text", "text": text}]}


def para(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


class TestSections:
    def test_split_at_headings(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                para("intro"),
                heading("Problem"),
                para("one"),
                para("two"),
                heading("Empty"),
                heading("Result"),
                {"type": "horizontalRule"},
                para("done"),
            ],
        }
        assert richtext.sections(doc) == [
            richtext.Section("", "intro"),
            richtext.Section("Problem", "one\ntwo"),
            richtext.Section("Result", "done"),
        ]

    def test_empty_document(self) -> None:
        assert richtext.sections(richtext.EMPTY_DOC) == []


def document(*sections: Section, lang: str = "en") -> SourceDocument:
    return SourceDocument(
        uuid4(),
        "project",
        "vizzion",
        lang,
        "Vizzion",
        "Urban AI",
        ("Vizzion", "Brusque"),
        ("gis",),
        sections,
    )


class TestChunking:
    def test_overview_then_sections(self) -> None:
        doc = document(Section("Problem", "Cities grow."), Section("", "Note."))
        chunks = chunk_document(doc)
        assert [(c.position, c.heading, c.text) for c in chunks] == [
            (0, "", "Urban AI\nVizzion · Brusque\ngis"),
            (1, "Problem", "Cities grow."),
            (2, "", "Note."),
        ]
        assert chunks[1].indexed_text == "Vizzion\nProblem\nCities grow."
        assert chunks[0].id == chunk_id(doc.entry_id, "en", 0)

    def test_ids_are_stable_and_language_specific(self) -> None:
        entry = uuid4()
        assert chunk_id(entry, "en", 1) == chunk_id(entry, "en", 1)
        assert chunk_id(entry, "en", 1) != chunk_id(entry, "pt", 1)

    def test_long_sections_are_packed_and_split(self) -> None:
        sentence = "word " * 50  # 250 chars
        paragraphs = "\n".join([sentence.strip()] * 8)  # 8 paragraphs of 249 chars
        long_paragraph = ("A sentence that goes on. " * 80).strip()  # ~2000 chars
        giant_word = "x" * (MAX_CHUNK_CHARS * 2 + 5)
        chunks = chunk_document(
            document(
                Section("A", paragraphs), Section("B", long_paragraph), Section("C", giant_word)
            )
        )
        assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
        assert [c.heading for c in chunks].count("A") == 2  # 8 x 250 packed into two
        assert [c.heading for c in chunks].count("B") >= 2  # split at sentence ends
        assert [len(c.text) for c in chunks if c.heading == "C"] == [1200, 1200, 5]

    def test_blank_lines_and_empty_sections_add_nothing(self) -> None:
        chunks = chunk_document(
            document(Section("A", "\n  \nfirst\n\nsecond\n"), Section("B", " \n "))
        )
        assert [(c.heading, c.text) for c in chunks[1:]] == [("A", "first\nsecond")]

    def test_overview_without_summary_or_tags(self) -> None:
        bare = SourceDocument(uuid4(), "study", "ddia", "en", "DDIA", "", (), (), ())
        [overview] = chunk_document(bare)
        assert (overview.text, overview.indexed_text) == ("", "DDIA")


class TestQuery:
    def test_normalizes_whitespace(self) -> None:
        assert SearchQuery.build("  rag   in\nproduction ", "pt", 3).text == "rag in production"

    @pytest.mark.parametrize(
        ("text", "lang", "limit", "reason"),
        [
            ("   ", "en", 5, "empty"),
            ("x" * 301, "en", 5, "limited"),
            ("rag", "fr", 5, "lang"),
            ("rag", "en", 0, "limit"),
            ("rag", "en", 21, "limit"),
        ],
    )
    def test_rejects(self, text: str, lang: str, limit: int, reason: str) -> None:
        with pytest.raises(InvalidQueryError, match=reason):
            SearchQuery.build(text, lang, limit)


@pytest.fixture
async def world() -> World:
    world = make_world()
    await seed(world)
    return world


class TestIndexAndSearch:
    async def test_search_before_any_index_is_empty(self) -> None:
        world = make_world()
        assert await world.search().search(SearchQuery.build("anything")) == []

    async def test_reindex_then_hybrid_search_in_each_language(self, world: World) -> None:
        search = world.search()
        chunks = await search.reindex()
        assert chunks > 0
        assert await search.reindex() == chunks  # rebuilding replaces, never duplicates
        assert set(world.sparse.langs) == {"en", "pt"}  # one stemmer per language
        [hit, *_] = await search.search(SearchQuery.build("Software Engineer Loopia", "en", 3))
        assert (hit.kind, hit.slug, hit.title) == ("experience", "loopia", "Software Engineer")
        [hit_pt, *_] = await search.search(SearchQuery.build("Engenheiro de software", "pt", 3))
        assert hit_pt.title == "Engenheiro de software"

    async def test_drafts_and_skills_are_not_indexed(self, world: World) -> None:
        search = world.search()
        await search.reindex()
        slugs = {
            h.slug for h in await search.search(SearchQuery.build("Secret COBOL Python", "en", 20))
        }
        assert "secret" not in slugs
        assert "python" not in slugs
        assert "cobol" not in slugs

    async def test_kind_filter(self, world: World) -> None:
        search = world.search()
        await search.reindex()
        hits = await search.search(SearchQuery.build("Vizzion Loopia", "en", 10, ("project",)))
        assert {h.kind for h in hits} == {"project"}

    async def test_falls_back_to_bm25_when_dense_fails(self, world: World) -> None:
        search = world.search()
        await search.reindex()
        world.dense.fail = True
        [hit, *_] = await search.search(SearchQuery.build("Loopia", "en", 3))
        assert hit.slug == "loopia"

    async def test_index_entry_follows_the_database(self, world: World) -> None:
        search, content = world.search(), world.container().content
        await search.reindex()
        loopia = next(e for e in await content.list(Kind.EXPERIENCE) if e.slug == "loopia")

        body = {"type": "doc", "content": [heading("Agents"), para("Hallucination control")]}
        draft = EntryDraft.build(
            Kind.EXPERIENCE,
            slug="loopia",
            translations={
                Lang.EN: Translation.create("Software Engineer", "s", body),
                Lang.PT: Translation.create("Engenheiro de software", "s"),
            },
            details=loopia.content.details,
        )
        loopia = await content.update(loopia.id, loopia.version, draft)
        assert await search.index_entry(loopia.id) == 3  # en overview + section, pt overview
        hits = await search.search(SearchQuery.build("hallucination control", "en", 1))
        assert hits[0].heading == "Agents"

        await content.unpublish(loopia.id, loopia.version)
        assert await search.index_entry(loopia.id) == 0
        remaining = await search.search(SearchQuery.build("Loopia", "en", 20))
        assert "loopia" not in {h.slug for h in remaining}

    async def test_removing_from_a_missing_collection_is_a_no_op(self) -> None:
        world = make_world()
        await world.index.delete_entry(uuid4())

    async def test_consumer_indexes_on_any_content_event(self, world: World) -> None:
        loopia = next(
            e for e in await world.container().content.list(Kind.EXPERIENCE) if e.slug == "loopia"
        )
        handle = consumer.handler(world.search().index_entry)
        await handle(Delivery("m", "content.entry.published", {"id": str(loopia.id)}, 1))
        hits = await world.search().search(SearchQuery.build("Loopia", "en", 5))
        assert {h.slug for h in hits} == {"loopia"}
        assert consumer.QUEUE.bindings == ("content.entry.*",)


class FakeArray:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def tolist(self) -> list[float]:
        return self.values


class FakeDenseModel:
    builds = 0

    def __init__(self) -> None:
        FakeDenseModel.builds += 1

    def embed(self, documents: Iterable[str], **_: Any) -> Iterable[Any]:
        return [FakeArray([float(len(d)), 1.0]) for d in documents]

    def query_embed(self, query: str, **_: Any) -> Iterable[Any]:
        return iter([FakeArray([float(len(query)), 0.0])])


class FakeBm25Model:
    def __init__(self, language: str) -> None:
        self.language = language

    def embed(self, documents: Iterable[str], **_: Any) -> Iterable[Any]:
        return [SimpleNamespace(indices=[1, 2], values=[0.5, 1.5]) for _ in documents]

    def query_embed(self, query: str, **_: Any) -> Iterable[Any]:
        return iter([SimpleNamespace(indices=[7], values=[1.0])])


class TestEncoders:
    async def test_dense_loads_once_and_converts(self) -> None:
        FakeDenseModel.builds = 0
        dense = FastembedDense(2, FakeDenseModel)
        assert FakeDenseModel.builds == 0  # lazy
        assert await dense.documents(["ab", "abc"]) == [[2.0, 1.0], [3.0, 1.0]]
        assert await dense.query("abcd") == [4.0, 0.0]
        assert (FakeDenseModel.builds, dense.dimension) == (1, 2)

    async def test_bm25_uses_a_stemmer_per_language(self) -> None:
        built: list[str] = []

        def build(language: str) -> FakeBm25Model:
            built.append(language)
            return FakeBm25Model(language)

        sparse = FastembedBm25(build)
        [vector] = await sparse.documents(["texto"], "pt")
        assert (vector.indices, vector.values) == ((1, 2), (0.5, 1.5))
        assert (await sparse.query("text", "en")).indices == (7,)
        assert built == ["portuguese", "english"]

    def test_factories_do_not_load_models(self) -> None:
        assert FastembedDense.create("some/model", 384, None).dimension == 384
        FastembedBm25.create(None)


@pytest.fixture
async def client(world: World) -> AsyncIterator[AsyncClient]:
    await world.search().reindex()
    async with AsyncClient(transport=ASGITransport(world.app()), base_url="https://a.t") as c:
        yield c


class TestHttp:
    async def test_search_endpoint(self, client: AsyncClient) -> None:
        response = await client.get("/api/search", params={"q": "Loopia", "kind": "experience"})
        [hit, *_] = response.json()
        assert (hit["slug"], hit["kind"]) == ("loopia", "experience")
        assert "cache-control" not in response.headers

    async def test_invalid_queries(self, client: AsyncClient) -> None:
        assert (await client.get("/api/search", params={"q": ""})).status_code == 422
        assert (await client.get("/api/search", params={"q": "   "})).status_code == 422
        assert (await client.get("/api/search", params={"q": "x", "limit": 50})).status_code == 422
