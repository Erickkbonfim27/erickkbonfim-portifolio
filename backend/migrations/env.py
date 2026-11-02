import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection

from portfolio.platform.db import Base, create_engine
from portfolio.platform.models import load_all_models

load_all_models()
target_metadata = Base.metadata


def _url() -> str:
    # Tests hand the URL of their temporary database through the Alembic config.
    # Only DATABASE_URL is read: migrating must not require the API's other settings.
    configured = context.config.attributes.get("database_url")
    return str(configured) if configured else os.environ["DATABASE_URL"]


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())
