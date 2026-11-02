"""The worker process: everything that must not run inside an HTTP request.

    outbox relay   publishes committed events to RabbitMQ
    consumers      react to events (contact emails now, search indexing in phase 4)
    scheduler      daily jobs, each run once across workers (advisory lock)

Run with `portfolio worker`. Stops cleanly on SIGTERM/SIGINT.
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import delete

from portfolio.bootstrap import (
    Infrastructure,
    build_infrastructure,
    close_infrastructure,
    contacts_uow,
    search_use_cases,
)
from portfolio.contexts.contacts.application.use_cases import NotifyContact, PurgeExpiredContacts
from portfolio.contexts.contacts.infrastructure.mailer import ResendMailer
from portfolio.contexts.contacts.interfaces import consumer as contacts_consumer
from portfolio.contexts.search.interfaces import consumer as search_consumer
from portfolio.platform.jobs import ScheduledJob, run_exclusive
from portfolio.platform.messaging import RabbitBroker
from portfolio.platform.outbox import OutboxRow, relay_once
from portfolio.platform.settings import Settings

log = logging.getLogger(__name__)

RELAY_IDLE = 1.0  # seconds between outbox polls when there is nothing to send
OUTBOX_KEEP = timedelta(days=30)
RATE_LIMIT_KEEP = timedelta(days=2)


class MissingWorkerSettingError(RuntimeError):
    pass


def _require(value: str | None, name: str) -> str:
    if not value:
        raise MissingWorkerSettingError(f"{name} is required to run the worker")
    return value


async def relay_forever(infra: Infrastructure, broker: RabbitBroker) -> None:
    while True:
        sent = await relay_once(infra.session_factory, broker, infra.clock.now())
        if sent == 0:
            await asyncio.sleep(RELAY_IDLE)


def housekeeping(infra: Infrastructure) -> Callable[[], Awaitable[str]]:
    async def run() -> str:
        now = infra.clock.now()
        limits = await infra.limiter.purge(now - RATE_LIMIT_KEEP)
        async with infra.session_factory() as session, session.begin():
            result = await session.execute(
                delete(OutboxRow).where(OutboxRow.published_at < now - OUTBOX_KEEP)
            )
        events = int(getattr(result, "rowcount", 0) or 0)
        return f"deleted {limits} rate-limit windows and {events} sent events"

    return run


def daily_jobs(infra: Infrastructure) -> list[ScheduledJob]:
    purge_contacts = PurgeExpiredContacts(contacts_uow(infra), infra.clock)
    return [
        ScheduledJob("purge-expired-contacts", hour=3, minute=0, run=purge_contacts),
        ScheduledJob("housekeeping", hour=3, minute=30, run=housekeeping(infra)),
    ]


def schedule(infra: Infrastructure, jobs: list[ScheduledJob]) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    for job in jobs:

        async def run(job: ScheduledJob = job) -> None:
            await run_exclusive(
                infra.engine, infra.session_factory, job.name, job.run, infra.clock.now
            )

        scheduler.add_job(run, CronTrigger(hour=job.hour, minute=job.minute, timezone="UTC"))
    return scheduler


async def run_worker(settings: Settings) -> None:  # pragma: no cover - wiring, needs services
    infra = build_infrastructure(settings)
    broker = RabbitBroker(_require(settings.rabbitmq_url, "RABBITMQ_URL"))
    http = httpx.AsyncClient()
    mailer = ResendMailer(
        http,
        _require(settings.resend_api_key, "RESEND_API_KEY"),
        _require(settings.mail_from, "MAIL_FROM"),
    )
    notify = NotifyContact(
        contacts_uow(infra), mailer, infra.clock, _require(settings.owner_email, "OWNER_EMAIL")
    )
    await broker.connect()
    scheduler = schedule(infra, daily_jobs(infra))
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    tasks = [
        asyncio.create_task(relay_forever(infra, broker), name="outbox-relay"),
        asyncio.create_task(
            broker.consume(contacts_consumer.QUEUE, contacts_consumer.handler(notify)),
            name="contacts-consumer",
        ),
        asyncio.create_task(
            broker.consume(
                search_consumer.QUEUE,
                search_consumer.handler(search_use_cases(infra).index_entry),
            ),
            name="search-indexer",
        ),
    ]
    log.info("worker started")
    await stop.wait()
    log.info("worker stopping")
    scheduler.shutdown(wait=False)
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task
    await broker.close()
    await http.aclose()
    await close_infrastructure(infra)
