from uuid import UUID, uuid4

import pytest

from portfolio.contexts.content.application.use_cases import ContentUseCases
from portfolio.contexts.content.domain.entry import Attachment, EntryDraft, Translation
from portfolio.contexts.content.domain.errors import (
    EntryNotFoundError,
    SingletonKindError,
    SlugTakenError,
    UnknownFileError,
    UnknownSkillError,
    VersionConflictError,
)
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status
from tests.unit.fakes import ContentStore, content_use_cases
from tests.unit.identity.fakes import FixedClock

BOTH = {Lang.EN: Translation.create("Title", "Summary"), Lang.PT: Translation.create("T", "Resumo")}


def experience(slug: str = "loopia", **overrides: object) -> EntryDraft:
    values: dict[str, object] = {
        "slug": slug,
        "translations": BOTH,
        "details": {"organization": "Loopia", "start": "2026-05"},
    }
    values.update(overrides)
    return EntryDraft.build(Kind.EXPERIENCE, **values)  # type: ignore[arg-type]


def skill(slug: str) -> EntryDraft:
    return EntryDraft.build(Kind.SKILL, slug=slug, translations=BOTH, details={"category": "ai"})


@pytest.fixture
def store() -> ContentStore:
    return ContentStore()


@pytest.fixture
def uc(store: ContentStore) -> ContentUseCases:
    return content_use_cases(store, FixedClock())


async def test_create_list_get(uc: ContentUseCases) -> None:
    entry = await uc.create(Kind.EXPERIENCE, experience())
    assert await uc.get(entry.id) == entry
    assert await uc.list(Kind.EXPERIENCE, Status.DRAFT) == [entry]
    assert await uc.list(Kind.PROJECT) == []


async def test_drafts_emit_no_events(uc: ContentUseCases, store: ContentStore) -> None:
    entry = await uc.create(Kind.EXPERIENCE, experience())
    await uc.update(entry.id, 1, experience(slug="loopia-2"))
    await uc.delete(entry.id)
    assert store.events == []


async def test_publish_update_unpublish_delete_emit_events(
    uc: ContentUseCases, store: ContentStore
) -> None:
    entry = await uc.create(Kind.EXPERIENCE, experience())
    entry = await uc.publish(entry.id, 1)
    entry = await uc.update(entry.id, 2, experience())
    entry = await uc.unpublish(entry.id, 3)
    entry = await uc.publish(entry.id, 4)
    await uc.delete(entry.id)
    assert [topic for topic, _ in store.events] == [
        "content.entry.published",
        "content.entry.published",
        "content.entry.unpublished",
        "content.entry.published",
        "content.entry.deleted",
    ]
    assert [payload.get("version") for _, payload in store.events] == [2, 3, 4, 5, None]


async def test_unpublishing_a_draft_is_a_no_op(uc: ContentUseCases, store: ContentStore) -> None:
    entry = await uc.create(Kind.EXPERIENCE, experience())
    assert await uc.unpublish(entry.id, 1) == entry
    assert store.events == []


async def test_stale_version_is_a_conflict(uc: ContentUseCases) -> None:
    entry = await uc.create(Kind.EXPERIENCE, experience())
    await uc.update(entry.id, 1, experience())
    with pytest.raises(VersionConflictError) as conflict:
        await uc.update(entry.id, 1, experience())
    assert conflict.value.current == 2


async def test_slug_unique_per_kind(uc: ContentUseCases) -> None:
    await uc.create(Kind.EXPERIENCE, experience())
    with pytest.raises(SlugTakenError):
        await uc.create(Kind.EXPERIENCE, experience())
    other = await uc.create(Kind.EXPERIENCE, experience(slug="silpi"))
    with pytest.raises(SlugTakenError):
        await uc.update(other.id, 1, experience(slug="loopia"))
    assert (await uc.create(Kind.SKILL, skill("loopia"))).slug == "loopia"


async def test_only_one_profile(uc: ContentUseCases) -> None:
    profile = EntryDraft.build(
        Kind.PROFILE, slug="erick", translations=BOTH, details={"name": "E", "availability": "open"}
    )
    await uc.create(Kind.PROFILE, profile)
    with pytest.raises(SingletonKindError):
        await uc.create(Kind.PROFILE, profile)


async def test_skills_must_be_skill_entries(uc: ContentUseCases) -> None:
    python = await uc.create(Kind.SKILL, skill("python"))
    project = await uc.create(Kind.EXPERIENCE, experience(slug="silpi"))
    entry = await uc.create(Kind.EXPERIENCE, experience(skills=[python.id]))
    assert entry.content.skills == (python.id,)
    for bad in (project.id, uuid4()):
        with pytest.raises(UnknownSkillError):
            await uc.create(Kind.EXPERIENCE, experience(slug=f"x-{bad.hex[:6]}", skills=[bad]))


async def test_attachments_must_exist(uc: ContentUseCases, store: ContentStore) -> None:
    missing = uuid4()
    with pytest.raises(UnknownFileError):
        await uc.create(Kind.EXPERIENCE, experience(attachments=[Attachment(missing, "CV")]))
    assert isinstance(store.files, set)
    store.files.add(missing)
    entry = await uc.create(Kind.EXPERIENCE, experience(attachments=[Attachment(missing, "CV")]))
    assert entry.content.attachments[0].label == "CV"


async def test_missing_entry(uc: ContentUseCases) -> None:
    missing: UUID = uuid4()
    with pytest.raises(EntryNotFoundError):
        await uc.get(missing)
    with pytest.raises(EntryNotFoundError):
        await uc.publish(missing, 1)
    with pytest.raises(EntryNotFoundError):
        await uc.delete(missing)
