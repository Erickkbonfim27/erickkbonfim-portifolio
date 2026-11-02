from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from tests.unit.support import World, make_world
from tests.unit.test_http import login

ENTRY: dict[str, Any] = {
    "kind": "experience",
    "slug": "loopia",
    "translations": {
        "en": {"title": "Software Engineer", "summary": "Integrations and agents"},
        "pt": {"title": "Engenheiro de software", "summary": "Integrações e agentes"},
    },
    "details": {"organization": "Loopia", "start": "2026-05", "end": "2026-10"},
    "tags": ["AI"],
}


@pytest.fixture
def world() -> World:
    return make_world()


@pytest.fixture
async def admin(world: World) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(world.app())
    async with AsyncClient(transport=transport, base_url="https://api.test") as client:
        await login(client, world)
        yield client


async def test_kinds_describe_the_forms(admin: AsyncClient) -> None:
    kinds = (await admin.get("/admin/content/kinds")).json()
    assert set(kinds) == {
        "profile",
        "experience",
        "project",
        "education",
        "certificate",
        "study",
        "writing",
        "post",
        "skill",
    }
    collection = next(f for f in kinds["project"] if f["name"] == "collection")
    assert collection == {
        "name": "collection",
        "type": "choice",
        "required": True,
        "choices": ["portfolio", "lab"],
    }


async def test_full_lifecycle(admin: AsyncClient, world: World) -> None:
    created = await admin.post("/admin/content/entries", json=ENTRY)
    assert created.status_code == 201
    entry = created.json()
    assert (entry["status"], entry["version"], entry["tags"]) == ("draft", 1, ["ai"])
    assert entry["translations"]["en"]["body"] == {"type": "doc", "content": []}
    url = f"/admin/content/entries/{entry['id']}"

    update = {**ENTRY, "version": 1, "slug": "loopia-ai"}
    del update["kind"]
    updated = (await admin.put(url, json=update)).json()
    assert (updated["slug"], updated["version"]) == ("loopia-ai", 2)

    published = (await admin.post(f"{url}/publish", json={"version": 2})).json()
    assert published["status"] == "published"
    assert published["published_at"] is not None
    listed = (await admin.get("/admin/content/entries?kind=experience&status=published")).json()
    assert [e["id"] for e in listed] == [entry["id"]]

    unpublished = (await admin.post(f"{url}/unpublish", json={"version": 3})).json()
    assert unpublished["status"] == "draft"
    assert (await admin.get(url)).json()["version"] == 4

    assert (await admin.delete(url)).status_code == 204
    assert (await admin.get(url)).status_code == 404
    assert [topic for topic, _ in world.content.events] == [
        "content.entry.published",
        "content.entry.unpublished",
    ]


async def test_errors_map_to_http(admin: AsyncClient) -> None:
    entry = (await admin.post("/admin/content/entries", json=ENTRY)).json()
    url = f"/admin/content/entries/{entry['id']}"

    duplicate = await admin.post("/admin/content/entries", json=ENTRY)
    assert duplicate.status_code == 409

    stale = await admin.post(f"{url}/publish", json={"version": 7})
    assert stale.status_code == 409
    assert stale.json()["current_version"] == 1

    invalid = await admin.post("/admin/content/entries", json={**ENTRY, "slug": "Bad Slug"})
    assert invalid.status_code == 422

    script = {"type": "doc", "content": [{"type": "script"}]}
    bad_body = {**ENTRY, "slug": "x", "translations": {"en": {"title": "t", "body": script}}}
    assert (await admin.post("/admin/content/entries", json=bad_body)).status_code == 422

    incomplete = {**ENTRY, "slug": "y", "translations": {"en": ENTRY["translations"]["en"]}}
    created = (await admin.post("/admin/content/entries", json=incomplete)).json()
    publish = await admin.post(
        f"/admin/content/entries/{created['id']}/publish", json={"version": 1}
    )
    assert publish.status_code == 422

    unknown_file = {**ENTRY, "slug": "z", "attachments": [{"file_id": str(uuid4()), "label": "CV"}]}
    assert (await admin.post("/admin/content/entries", json=unknown_file)).status_code == 422

    assert (await admin.get(f"/admin/content/entries/{uuid4()}")).status_code == 404
