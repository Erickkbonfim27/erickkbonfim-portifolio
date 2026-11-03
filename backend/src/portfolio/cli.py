"""`portfolio <command>`: operational commands, run by hand through `make`."""

import argparse
import asyncio
import getpass
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from portfolio.bootstrap import (
    Container,
    build_container,
    build_infrastructure,
    close_infrastructure,
    search_use_cases,
)
from portfolio.contexts.assistant.application.evals import RunEval
from portfolio.contexts.assistant.domain import prompts
from portfolio.contexts.assistant.interfaces import cli as assistant_cli
from portfolio.contexts.content.interfaces import seed as content_seed
from portfolio.contexts.identity.interfaces import cli as identity_cli
from portfolio.platform.settings import Settings


async def _create_admin(container: Container) -> int:
    try:
        return await identity_cli.create_admin(
            container.identity.create_admin, ask=input, ask_secret=getpass.getpass, say=print
        )
    finally:
        await container.close()


async def _seed(container: Container, paths: list[Path]) -> int:
    async def upload(path: Path) -> str:
        data = await asyncio.to_thread(path.read_bytes)
        return (await container.files.upload(path.name, data)).url

    try:
        return await content_seed.seed(container.content, paths, say=print, upload=upload)
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


async def _eval(settings: Settings, path: Path, min_pass: float, only: list[str]) -> int:
    # Eval traces stay apart from the site's in Langfuse.
    settings = settings.model_copy(update={"langfuse_environment": "eval"})
    infra = build_infrastructure(settings)
    container = build_container(settings, infra)
    try:
        return await assistant_cli.run(
            RunEval(container.assistant.agent, infra.langfuse),
            path,
            now=datetime.now(UTC),
            min_pass=min_pass,
            only=only,
            metadata={
                "models": {"fast": settings.chat_models, "strong": settings.chat_models_strong},
                "prompts": {
                    name: prompts.load(name).version
                    for name in ("system", "rewrite", "grounding", "synthesis")
                },
            },
            say=print,
        )
    finally:
        await container.close()


def main(argv: list[str] | None = None, container: Container | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-admin", help="create the admin account (asks for the password)")
    commands.add_parser("worker", help="outbox relay, message consumers and daily jobs")
    commands.add_parser("setup-storage", help="create the bucket and its public-read policy")
    commands.add_parser("reindex", help="rebuild the search index from published content")
    seed = commands.add_parser("seed", help="create, update and publish content from TOML files")
    seed.add_argument("paths", nargs="+", type=Path, help="TOML files or directories of them")
    evals = commands.add_parser("eval", help="run the agent's dataset, score it, sync to Langfuse")
    evals.add_argument("dataset", type=Path, nargs="?", default=Path("evals/assistant.jsonl"))
    evals.add_argument("--min-pass", type=float, default=0.9, help="share of cases that must pass")
    evals.add_argument("--only", nargs="*", default=[], help="case ids to run")
    args = parser.parse_args(argv)
    command = args.command

    if command == "create-admin":
        return asyncio.run(_create_admin(container or build_container(Settings())))
    if command == "seed":
        return asyncio.run(_seed(container or build_container(Settings()), args.paths))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if command == "setup-storage":
        return asyncio.run(_setup_storage(Settings()))
    if command == "reindex":
        return asyncio.run(_reindex(Settings()))
    if command == "eval":
        logging.getLogger("httpx").setLevel(logging.WARNING)
        return asyncio.run(_eval(Settings(), args.dataset, args.min_pass, args.only))
    from portfolio.worker import run_worker  # noqa: PLC0415 - the API never imports the worker

    asyncio.run(run_worker(Settings()))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
