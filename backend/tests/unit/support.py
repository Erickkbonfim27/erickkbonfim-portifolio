"""A whole app wired with fakes, for HTTP-level unit tests."""

from dataclasses import dataclass, field

from fastapi import FastAPI
from qdrant_client import AsyncQdrantClient

from portfolio.bootstrap import Container
from portfolio.bridges import ContentSourceCatalog
from portfolio.contexts.content.application.catalog import IndexFeed
from portfolio.contexts.identity.interfaces.http import AuthCookie
from portfolio.contexts.search.application.use_cases import (
    IndexEntry,
    Reindex,
    Search,
    SearchUseCases,
    writer,
)
from portfolio.contexts.search.infrastructure.qdrant_index import QdrantIndex
from portfolio.main import create_app
from portfolio.platform.settings import Settings
from tests.unit.fakes import (
    ContactsStore,
    ContentStore,
    FakeLimiter,
    FakeStorage,
    FilesStore,
    InMemoryContentUoW,
    LiveFileIds,
    contacts_use_cases,
    content_catalog,
    content_use_cases,
    files_use_cases,
)
from tests.unit.identity.fakes import FixedClock, Harness, make_harness
from tests.unit.search.fakes import HashingDense, HashingSparse

COOKIE = "ekb_session"

REQUIRED_SETTINGS: dict[str, object] = {
    "database_url": "postgresql+asyncpg://unused/unused",
    "s3_endpoint_url": "http://minio.test",
    "s3_access_key": "key",
    "s3_secret_key": "secret",
    "s3_bucket": "portfolio",
    "public_files_base_url": "https://files.test/",
    "ip_hash_secret": "x" * 32,
    "public_site_url": "https://erick.test/",
    "public_api_url": "https://api.erick.test",
    "qdrant_url": "http://qdrant.test:6333",
    "openrouter_api_key": "sk-or-test",
}


def settings_for_tests(**overrides: object) -> Settings:
    values = {**REQUIRED_SETTINGS, "cors_origins": ["https://erick.dev"], **overrides}
    return Settings.model_validate(values)


class Closer:
    def __init__(self) -> None:
        self.closed = False

    async def __call__(self) -> None:
        self.closed = True


@dataclass
class World:
    identity: Harness
    content: ContentStore
    files: FilesStore
    storage: FakeStorage
    contacts: ContactsStore
    limiter: FakeLimiter
    closer: Closer
    dense: HashingDense = field(default_factory=HashingDense)
    sparse: HashingSparse = field(default_factory=HashingSparse)
    # Qdrant's local mode: the real adapter and real query API, in memory.
    index: QdrantIndex = field(
        default_factory=lambda: QdrantIndex(AsyncQdrantClient(location=":memory:"), "portfolio")
    )

    def search(self) -> SearchUseCases:
        feed = ContentSourceCatalog(IndexFeed(lambda: InMemoryContentUoW(self.content)))
        write = writer(self.dense, self.sparse, self.index)
        return SearchUseCases(
            index_entry=IndexEntry(feed, write),
            reindex=Reindex(feed, write),
            search=Search(self.dense, self.sparse, self.index),
        )

    @property
    def clock(self) -> FixedClock:
        return self.identity.clock

    def container(self) -> Container:
        clock = self.identity.clock
        files = files_use_cases(self.files, self.storage, clock)
        return Container(
            identity=self.identity.use_cases,
            content=content_use_cases(self.content, clock),
            catalog=content_catalog(self.content, files),
            search=self.search().search,
            files=files,
            contacts=contacts_use_cases(self.contacts, self.limiter, clock),
            auth_cookie=AuthCookie(name=COOKIE, secure=True, domain=None),
            close=self.closer,
        )

    def app(self, **settings: object) -> FastAPI:
        return create_app(settings_for_tests(**settings), self.container())


def make_world() -> World:
    files = FilesStore()
    return World(
        identity=make_harness(),
        content=ContentStore(files=LiveFileIds(files)),
        files=files,
        storage=FakeStorage(),
        contacts=ContactsStore(),
        limiter=FakeLimiter(),
        closer=Closer(),
    )
