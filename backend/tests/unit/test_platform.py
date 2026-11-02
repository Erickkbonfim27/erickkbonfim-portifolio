import pytest

from portfolio.bootstrap import (
    build_container,
    build_infrastructure,
    close_infrastructure,
    contacts_uow,
    search_use_cases,
)
from portfolio.contexts.contacts.infrastructure.persistence import SqlContactsUnitOfWork
from portfolio.contexts.content.infrastructure.persistence import SqlContentUnitOfWork
from portfolio.contexts.files.infrastructure.persistence import SqlFilesUnitOfWork
from portfolio.contexts.identity.infrastructure.persistence import SqlIdentityUnitOfWork
from portfolio.main import create_app
from portfolio.platform.clock import SystemClock
from portfolio.platform.db import Base, asyncpg_url, create_engine
from portfolio.platform.models import load_all_models
from portfolio.platform.settings import Settings
from tests.unit.support import REQUIRED_SETTINGS, settings_for_tests


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED_SETTINGS.items():
        monkeypatch.setenv(name.upper(), str(value))


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://erick.dev, http://localhost:5173,")
    monkeypatch.setenv("COOKIE_DOMAIN", "")
    monkeypatch.setenv("RABBITMQ_URL", "")
    settings = Settings()
    assert settings.cors_origins == ["https://erick.dev", "http://localhost:5173"]
    assert settings.cookie_domain is None
    assert settings.rabbitmq_url is None
    assert settings.public_files_base_url == "https://files.test"
    assert settings.cookie_secure is True


def test_settings_accept_python_values() -> None:
    settings = settings_for_tests(cors_origins=["https://a.dev"], cookie_domain=".a.dev")
    assert settings.cors_origins == ["https://a.dev"]
    assert settings.cookie_domain == ".a.dev"


def test_required_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="database_url"):
        Settings()


def test_cors_origins_cannot_be_a_wildcard() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        settings_for_tests(cors_origins=["https://erick.dev", "*"])


def test_s3_endpoint_cannot_use_an_internal_easypanel_name() -> None:
    with pytest.raises(ValueError, match="public domain"):
        settings_for_tests(s3_endpoint_url="http://portifolio_rustfs:9000")


def test_ip_hash_secret_must_be_long() -> None:
    with pytest.raises(ValueError, match="ip_hash_secret"):
        settings_for_tests(ip_hash_secret="short")


async def test_container_wiring_does_not_connect() -> None:
    settings = settings_for_tests(session_ttl_hours=2)
    infra = build_infrastructure(settings)
    container = build_container(settings, infra)
    assert container.auth_cookie.name == "ekb_session"
    assert container.identity.login.session_ttl.total_seconds() == 7200
    assert container.identity.login.dummy_password_hash.startswith("$argon2id$")
    assert isinstance(container.identity.logout.uow(), SqlIdentityUnitOfWork)
    assert isinstance(container.content.get.uow(), SqlContentUnitOfWork)
    assert isinstance(container.catalog.uow(), SqlContentUnitOfWork)
    assert container.catalog.render.image_base_url == "https://files.test"
    assert isinstance(container.files.list.uow(), SqlFilesUnitOfWork)
    assert isinstance(contacts_uow(infra)(), SqlContactsUnitOfWork)
    assert infra.storage.public_url("a.pdf") == "https://files.test/a.pdf"
    search = search_use_cases(infra)
    assert search.search.index is infra.index
    assert infra.qdrant._client.rest_uri == "http://qdrant.test:6333"  # type: ignore[attr-defined]
    assert isinstance(search.index_entry.catalog._feed.uow(), SqlContentUnitOfWork)  # type: ignore[attr-defined]
    await container.close()
    await close_infrastructure(build_infrastructure(settings))


def test_app_builds_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    assert create_app().title.startswith("Erick Kopak Bonfim")


def test_every_model_is_registered() -> None:
    load_all_models()
    assert {
        "identity_admin_users",
        "identity_sessions",
        "content_entries",
        "content_translations",
        "content_entry_skills",
        "content_attachments",
        "files_objects",
        "contacts_requests",
        "platform_outbox",
        "platform_rate_limits",
        "platform_job_runs",
    } <= set(Base.metadata.tables)


def test_system_clock_is_timezone_aware() -> None:
    assert SystemClock().now().tzinfo is not None


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("postgresql://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("postgresql+asyncpg://u:p@db/app", "postgresql+asyncpg://u:p@db/app"),
        (
            "postgres://u:p%40ss@db:5432/app?sslmode=disable",
            "postgresql+asyncpg://u:p%40ss@db:5432/app?ssl=disable",
        ),
        (
            "postgres://u:p@db/app?sslmode=require&sslmode=disable",
            "postgresql+asyncpg://u:p@db/app?ssl=disable",
        ),
        ("sqlite://", "sqlite://"),
    ],
)
def test_database_urls_from_hosting_panels(given: str, expected: str) -> None:
    assert asyncpg_url(given) == expected


async def test_engine_uses_asyncpg_for_a_panel_url() -> None:
    engine = create_engine("postgres://u:p@db:5432/app")
    assert engine.url.drivername == "postgresql+asyncpg"
    await engine.dispose()


async def test_a_qdrant_url_without_port_uses_the_scheme_default() -> None:
    infra = build_infrastructure(settings_for_tests(qdrant_url="https://qdrant.example.dev"))
    assert infra.qdrant._client.rest_uri == "https://qdrant.example.dev"  # type: ignore[attr-defined]
    await close_infrastructure(infra)
