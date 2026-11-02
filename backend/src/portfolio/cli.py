"""`portfolio <command>`: operational commands, run by hand through `make`."""

import argparse
import asyncio
import getpass
import logging
import sys

from portfolio.bootstrap import (
    Container,
    build_container,
    build_infrastructure,
    close_infrastructure,
    search_use_cases,
)
from portfolio.contexts.identity.interfaces import cli as identity_cli
from portfolio.platform.settings import Settings


async def _create_admin(container: Container) -> int:
    try:
        return await identity_cli.create_admin(
            container.identity.create_admin, ask=input, ask_secret=getpass.getpass, say=print
        )
    finally:
        await container.close()


async def _setup_storage(settings: Settings) -> int:
    infra = build_infrastructure(settings)
    try:
        await infra.storage.ensure_bucket()
    finally:
        await close_infrastructure(infra)
    print(f"Bucket {settings.s3_bucket} ready: public read, no listing.")
    return 0


async def _reindex(settings: Settings) -> int:
    infra = build_infrastructure(settings)
    try:
        chunks = await search_use_cases(infra).reindex()
    finally:
        await close_infrastructure(infra)
    print(f"Index rebuilt: {chunks} chunks.")
    return 0


def main(argv: list[str] | None = None, container: Container | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-admin", help="create the admin account (asks for the password)")
    commands.add_parser("worker", help="outbox relay, message consumers and daily jobs")
    commands.add_parser("setup-storage", help="create the bucket and its public-read policy")
    commands.add_parser("reindex", help="rebuild the search index from published content")
    command = parser.parse_args(argv).command

    if command == "create-admin":
        return asyncio.run(_create_admin(container or build_container(Settings())))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if command == "setup-storage":
        return asyncio.run(_setup_storage(Settings()))
    if command == "reindex":
        return asyncio.run(_reindex(Settings()))
    from portfolio.worker import run_worker  # noqa: PLC0415 - the API never imports the worker

    asyncio.run(run_worker(Settings()))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
