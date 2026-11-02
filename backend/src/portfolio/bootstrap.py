"""Composition root: the only place that knows every concrete adapter."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from portfolio.bridges import ContentSourceCatalog, FilesAttachmentCatalog
from portfolio.contexts.contacts.application.use_cases import (
    ContactsUseCases,
    DeleteContact,
    GetContact,
    ListContacts,
    PurgeExpiredContacts,
    SetContactStatus,
    SubmitContact,
)
from portfolio.contexts.contacts.infrastructure.persistence import SqlContactsUnitOfWork
from portfolio.contexts.content.application.catalog import IndexFeed, PublicCatalog
from portfolio.contexts.content.application.use_cases import (
    ContentUseCases,
    CreateEntry,
    DeleteEntry,
    GetEntry,
    ListEntries,
    PublishEntry,
    UnpublishEntry,
    UpdateEntry,
)
from portfolio.contexts.content.domain.richtext import RenderOptions
from portfolio.contexts.content.infrastructure.persistence import SqlContentUnitOfWork
from portfolio.contexts.files.application.use_cases import (
    DeleteFile,
    DescribeFiles,
    FilesUseCases,
    ListFiles,
    UploadFile,
)
from portfolio.contexts.files.infrastructure.persistence import SqlFilesUnitOfWork
from portfolio.contexts.files.infrastructure.storage import S3Storage, create_s3_client
from portfolio.contexts.identity.application.use_cases import (
    Authenticate,
    CreateAdmin,
    IdentityUseCases,
    Login,
    Logout,
)
from portfolio.contexts.identity.infrastructure.persistence import SqlIdentityUnitOfWork
from portfolio.contexts.identity.infrastructure.security import (
    Argon2PasswordHasher,
    UrlSafeTokenGenerator,
)
from portfolio.contexts.identity.interfaces.http import AuthCookie
from portfolio.contexts.search.application.use_cases import (
    IndexEntry,
    Reindex,
    Search,
    SearchUseCases,
    writer,
)
from portfolio.contexts.search.infrastructure.encoders import FastembedBm25, FastembedDense
from portfolio.contexts.search.infrastructure.qdrant_index import QdrantIndex
from portfolio.platform.clock import SystemClock
from portfolio.platform.db import create_engine, create_session_factory
from portfolio.platform.ratelimit import PostgresRateLimiter
from portfolio.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class Infrastructure:
    """Shared adapters, built once per process (API or worker)."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    clock: SystemClock
    storage: S3Storage
    limiter: PostgresRateLimiter
    qdrant: AsyncQdrantClient
    index: QdrantIndex
    dense: FastembedDense
    sparse: FastembedBm25


def build_infrastructure(settings: Settings) -> Infrastructure:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    clock = SystemClock()
    s3 = create_s3_client(
        settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key, settings.s3_region
    )
    # No version handshake at construction: it is a network call that would stall
    # startup whenever Qdrant is down. Client and server versions are pinned instead.
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, check_compatibility=False
    )
    return Infrastructure(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        clock=clock,
        storage=S3Storage(s3, settings.s3_bucket, settings.public_files_base_url),
        limiter=PostgresRateLimiter(session_factory, settings.ip_hash_secret, clock.now),
        qdrant=qdrant,
        index=QdrantIndex(qdrant, settings.qdrant_collection),
        # Loaded lazily on first use: an API that never searches never loads them.
        dense=FastembedDense.create(
            settings.dense_model, settings.dense_dimension, settings.fastembed_cache_dir
        ),
        sparse=FastembedBm25.create(settings.fastembed_cache_dir),
    )


async def close_infrastructure(infra: Infrastructure) -> None:
    await infra.qdrant.close()
    await infra.engine.dispose()


def search_use_cases(infra: Infrastructure) -> SearchUseCases:
    feed = ContentSourceCatalog(
        IndexFeed(lambda: SqlContentUnitOfWork(infra.session_factory, infra.clock.now))
    )
    write = writer(infra.dense, infra.sparse, infra.index)
    return SearchUseCases(
        index_entry=IndexEntry(feed, write),
        reindex=Reindex(feed, write),
        search=Search(infra.dense, infra.sparse, infra.index),
    )


def contacts_uow(infra: Infrastructure) -> Callable[[], SqlContactsUnitOfWork]:
    return lambda: SqlContactsUnitOfWork(infra.session_factory, infra.clock.now)


@dataclass(frozen=True, slots=True)
class Container:
    identity: IdentityUseCases
    content: ContentUseCases
    catalog: PublicCatalog
    search: Search
    files: FilesUseCases
    contacts: ContactsUseCases
    auth_cookie: AuthCookie
    close: Callable[[], Awaitable[None]]


def build_container(settings: Settings, infra: Infrastructure | None = None) -> Container:
    infra = infra or build_infrastructure(settings)
    clock = infra.clock

    def identity_uow() -> SqlIdentityUnitOfWork:
        return SqlIdentityUnitOfWork(infra.session_factory)

    def content_uow() -> SqlContentUnitOfWork:
        return SqlContentUnitOfWork(infra.session_factory, clock.now)

    def files_uow() -> SqlFilesUnitOfWork:
        return SqlFilesUnitOfWork(infra.session_factory)

    hasher = Argon2PasswordHasher()
    contacts = contacts_uow(infra)
    describe_files = DescribeFiles(files_uow, infra.storage)
    return Container(
        identity=IdentityUseCases(
            create_admin=CreateAdmin(uow=identity_uow, hasher=hasher, clock=clock),
            login=Login(
                uow=identity_uow,
                hasher=hasher,
                tokens=UrlSafeTokenGenerator(),
                clock=clock,
                session_ttl=timedelta(hours=settings.session_ttl_hours),
                dummy_password_hash=hasher.hash(uuid4().hex),
            ),
            logout=Logout(uow=identity_uow),
            authenticate=Authenticate(uow=identity_uow, clock=clock),
        ),
        content=ContentUseCases(
            create=CreateEntry(content_uow, clock),
            update=UpdateEntry(content_uow, clock),
            publish=PublishEntry(content_uow, clock),
            unpublish=UnpublishEntry(content_uow, clock),
            delete=DeleteEntry(content_uow),
            get=GetEntry(content_uow),
            list=ListEntries(content_uow),
        ),
        catalog=PublicCatalog(
            uow=content_uow,
            files=FilesAttachmentCatalog(describe_files),
            render=RenderOptions(image_base_url=settings.public_files_base_url),
        ),
        search=search_use_cases(infra).search,
        files=FilesUseCases(
            upload=UploadFile(files_uow, infra.storage, clock),
            list=ListFiles(files_uow, infra.storage),
            describe=describe_files,
            delete=DeleteFile(files_uow, infra.storage),
        ),
        contacts=ContactsUseCases(
            submit=SubmitContact(contacts, infra.limiter, clock),
            list=ListContacts(contacts),
            get=GetContact(contacts),
            set_status=SetContactStatus(contacts),
            delete=DeleteContact(contacts),
            purge_expired=PurgeExpiredContacts(contacts, clock),
        ),
        auth_cookie=AuthCookie(
            name=settings.session_cookie_name,
            secure=settings.cookie_secure,
            domain=settings.cookie_domain,
        ),
        close=lambda: close_infrastructure(infra),
    )
