"""RabbitMQ entry point of this context: emails for each new contact request."""

from uuid import UUID

from portfolio.contexts.contacts.application.use_cases import CONTACT_RECEIVED, NotifyContact
from portfolio.platform.messaging import Delivery, Handler, QueueSpec

QUEUE = QueueSpec("contacts.notify", bindings=(CONTACT_RECEIVED,))


def handler(notify: NotifyContact) -> Handler:
    async def on_contact_received(delivery: Delivery) -> None:
        await notify(UUID(str(delivery.payload["id"])))

    return on_contact_received
