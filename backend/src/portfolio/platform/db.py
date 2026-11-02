from sqlalchemy import MetaData
from sqlalchemy.engine import make_url
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
    """Accept the URL as hosting panels hand it out and point it at asyncpg.

    postgres:// and postgresql:// get the asyncpg driver, and libpq's `sslmode`
    (Easypanel adds `?sslmode=disable`) becomes asyncpg's `ssl`, which takes the
    same values. asyncpg rejects `sslmode` on every connection otherwise.
    """
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername == "postgresql+asyncpg" and "sslmode" in url.query:
        mode = url.query["sslmode"]
        ssl = mode if isinstance(mode, str) else mode[-1]  # repeated: the last one wins
        url = url.difference_update_query(["sslmode"]).update_query_dict({"ssl": ssl})
    return url.render_as_string(hide_password=False)


def create_engine(database_url: str) -> AsyncEngine:
    # Small pool: one VPS, low traffic. pre_ping survives the database restarting.
    return create_async_engine(
        asyncpg_url(database_url), pool_size=5, max_overflow=5, pool_pre_ping=True
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
