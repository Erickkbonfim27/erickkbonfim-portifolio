from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names, so Alembic migrations are stable and reviewable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def asyncpg_url(database_url: str) -> str:
    """Accept the URL as hosting panels hand it out (postgres://, postgresql://)
    and point it at the asyncpg driver. An explicit driver is left as given."""
    scheme, separator, rest = database_url.partition("://")
    if separator and scheme in {"postgres", "postgresql"}:
        return f"postgresql+asyncpg://{rest}"
    return database_url


def create_engine(database_url: str) -> AsyncEngine:
    # Small pool: one VPS, low traffic. pre_ping survives the database restarting.
    return create_async_engine(
        asyncpg_url(database_url), pool_size=5, max_overflow=5, pool_pre_ping=True
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
