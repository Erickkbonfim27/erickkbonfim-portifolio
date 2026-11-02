"""One temporary PostgreSQL database for the whole integration run.

Created once per session from TEST_DATABASE_ADMIN_URL, migrated (and the
migrations checked for reversibility), shared by every integration test, and
dropped at the end. Each test runs inside a transaction that is rolled back, so
tests never see each other's rows and nothing needs truncating.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as raw_engine

from portfolio.platform.db import asyncpg_url, create_engine

BACKEND = Path(__file__).resolve().parents[2]


def _migrate(url: str, *steps: tuple[str, str]) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["database_url"] = url
    for direction, target in steps:
        getattr(command, direction)(config, target)


@pytest.fixture(scope="session")
async def database_url() -> AsyncIterator[str]:
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL is not set")
    admin_url = asyncpg_url(admin_url)
    name = f"portfolio_test_{uuid4().hex[:12]}"
    # CREATE/DROP DATABASE cannot run inside a transaction.
    admin = raw_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.rsplit("/", 1)[0] + f"/{name}"
    try:
        # Alembic's env.py runs its own event loop, so it goes to a thread.
        await asyncio.to_thread(
            _migrate, url, ("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")
        )
        yield url
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions bound to one outer transaction; their commits become savepoints."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        yield async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await outer.rollback()
