"""RabbitMQ entry point: keep the index in line with published content."""

from uuid import UUID

from portfolio.contexts.search.application.use_cases import IndexEntry
from portfolio.platform.messaging import Delivery, Handler, QueueSpec

# Published, unpublished and deleted all mean the same thing here: make the index
# match the database for this entry.
QUEUE = QueueSpec("search.index", bindings=("content.entry.*",))


def handler(index_entry: IndexEntry) -> Handler:
    async def on_content_changed(delivery: Delivery) -> None:
        await index_entry(UUID(str(delivery.payload["id"])))

    return on_content_changed
