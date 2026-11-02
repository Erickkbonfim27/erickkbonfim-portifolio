"""Events other parts of the system react to (the search indexer, from phase 4).

Only published content produces events: drafts are invisible outside the admin.
Each event carries the entry version, so a consumer can ignore stale deliveries.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from portfolio.contexts.content.domain.entry import Entry


@dataclass(frozen=True, slots=True)
class ContentEvent:
    topic: str
    payload: dict[str, Any]


def entry_published(entry: Entry) -> ContentEvent:
    return ContentEvent(
        "content.entry.published",
        {
            "id": str(entry.id),
            "kind": entry.kind.value,
            "slug": entry.slug,
            "version": entry.version,
        },
    )


def entry_unpublished(entry: Entry) -> ContentEvent:
    return ContentEvent(
        "content.entry.unpublished", {"id": str(entry.id), "version": entry.version}
    )


def entry_deleted(entry_id: UUID) -> ContentEvent:
    return ContentEvent("content.entry.deleted", {"id": str(entry_id)})
