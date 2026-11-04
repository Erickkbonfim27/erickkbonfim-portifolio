from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from portfolio.contexts.content.domain.details import parse_details
from portfolio.contexts.content.domain.entry import Attachment, Entry, EntryDraft, Translation
from portfolio.contexts.content.domain.errors import (
    EntryNotFoundError,
    IncompleteEntryError,
    InvalidEntryError,
    VersionConflictError,
)
from portfolio.contexts.content.domain.events import entry_deleted, entry_published
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status
from tests.unit.identity.fakes import START

BODY = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "b"}]}],
}
BOTH = {
    Lang.EN: Translation.create("Title", "Summary"),
    Lang.PT: Translation.create("Título", "Resumo"),
}
EXPERIENCE = {"organization": "Vizzion", "start": "2024-03", "end": "2025-10"}


def draft(kind: Kind = Kind.EXPERIENCE, **overrides: Any) -> EntryDraft:
    values: dict[str, Any] = {
        "slug": "vizzion",
        "translations": BOTH,
        "details": EXPERIENCE if kind is Kind.EXPERIENCE else {"category": "ai"},
    }
    values.update(overrides)
    return EntryDraft.build(kind, **values)


class TestDetails:
    def test_valid_experience(self) -> None:
        details = {
            **EXPERIENCE,
            "url": "https://vizzion.dev",
            "employment": "founder",
            "location": "",
        }
        assert parse_details(Kind.EXPERIENCE, details) == {
            "organization": "Vizzion",
            "start": "2024-03",
            "end": "2025-10",
            "url": "https://vizzion.dev",
            "employment": "founder",
        }

    def test_profile_fields(self) -> None:
        parsed = parse_details(
            Kind.PROFILE,
            {
                "name": " Erick ",
                "email": "E@x.dev",
                "availability": "open",
                "links": [{"label": "GitHub", "url": "https://github.com/x"}],
                "availability_updated_at": "ignored-server-managed",
            },
        )
        assert parsed == {
            "name": "Erick",
            "email": "e@x.dev",
            "availability": "open",
            "links": [{"label": "GitHub", "url": "https://github.com/x"}],
        }

    def test_a_provider_lists_its_services(self) -> None:
        parsed = parse_details(
            Kind.SKILL, {"category": "cloud", "services": [" Lambda ", "SQS / SQS FIFO"]}
        )
        assert parsed == {"category": "cloud", "services": ["Lambda", "SQS / SQS FIFO"]}

    @pytest.mark.parametrize(
        ("kind", "details", "reason"),
        [
            (Kind.EXPERIENCE, {**EXPERIENCE, "salary": 1}, "unknown fields"),
            (Kind.EXPERIENCE, {"start": "2024-01"}, "organization is required"),
            (Kind.EXPERIENCE, {**EXPERIENCE, "start": "2024-13"}, "YYYY-MM"),
            (Kind.EXPERIENCE, {**EXPERIENCE, "end": "2020-01"}, "before start"),
            (Kind.EXPERIENCE, {**EXPERIENCE, "url": "javascript:x"}, "http"),
            (Kind.EXPERIENCE, {**EXPERIENCE, "url": 7}, "URL"),
            (Kind.EXPERIENCE, {**EXPERIENCE, "organization": "x" * 200}, "text up to"),
            (Kind.EXPERIENCE, {**EXPERIENCE, "employment": "slave"}, "one of"),
            (Kind.PROFILE, {"name": "E", "availability": "open", "email": "nope"}, "email"),
            (Kind.PROFILE, {"name": "E", "availability": "open", "links": "x"}, "list"),
            (Kind.PROFILE, {"name": "E", "availability": "open", "links": [{"url": "x"}]}, "label"),
            (Kind.SKILL, {"category": "cloud", "services": "Lambda"}, "list of up to"),
            (Kind.SKILL, {"category": "cloud", "services": ["S3"] * 41}, "list of up to"),
            (Kind.SKILL, {"category": "cloud", "services": ["S3", " S3"]}, "repeat"),
            (Kind.SKILL, {"category": "cloud", "services": [""]}, "text up to"),
        ],
    )
    def test_rejects(self, kind: Kind, details: dict[str, Any], reason: str) -> None:
        with pytest.raises(InvalidEntryError, match=reason):
            parse_details(kind, details)


class TestDraft:
    def test_normalizes(self) -> None:
        skill = uuid4()
        file_id = uuid4()
        built = draft(
            tags=[" AI ", "ai", "", "RAG"],
            skills=[skill, skill],
            attachments=[Attachment(file_id, "  CV  ")],
        )
        assert built.tags == ("ai", "rag")
        assert built.skills == (skill,)
        assert built.attachments == (Attachment(file_id, "CV"),)

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"slug": "Not A Slug"}, "slug"),
            ({"slug": "a" * 81}, "slug"),
            ({"translations": {}}, "at least one language"),
            ({"tags": ["x" * 41]}, "tags"),
            ({"tags": [str(i) for i in range(21)]}, "tags"),
            ({"skills": [uuid4() for _ in range(61)]}, "skills"),
            ({"attachments": [Attachment(uuid4(), "a") for _ in range(21)]}, "attachments"),
            ({"position": 10**7}, "position"),
        ],
    )
    def test_rejects(self, overrides: dict[str, Any], reason: str) -> None:
        with pytest.raises(InvalidEntryError, match=reason):
            draft(**overrides)

    def test_rejects_duplicate_or_unlabelled_attachments(self) -> None:
        same = uuid4()
        with pytest.raises(InvalidEntryError, match="twice"):
            draft(attachments=[Attachment(same, "a"), Attachment(same, "b")])
        with pytest.raises(InvalidEntryError, match="labels"):
            draft(attachments=[Attachment(uuid4(), "  ")])

    def test_a_skill_cannot_list_skills(self) -> None:
        with pytest.raises(InvalidEntryError, match="skill cannot"):
            draft(Kind.SKILL, skills=[uuid4()])

    @pytest.mark.parametrize(
        ("title", "summary", "reason"), [("x" * 201, "", "title"), ("t", "x" * 601, "summary")]
    )
    def test_translation_limits(self, title: str, summary: str, reason: str) -> None:
        with pytest.raises(InvalidEntryError, match=reason):
            Translation.create(title, summary)


class TestLifecycle:
    def test_new_entries_are_drafts_at_version_1(self) -> None:
        entry = Entry.new(uuid4(), Kind.EXPERIENCE, draft(), START)
        assert (entry.status, entry.version, entry.slug) == (Status.DRAFT, 1, "vizzion")

    def test_edit_bumps_the_version(self) -> None:
        entry = Entry.new(uuid4(), Kind.EXPERIENCE, draft(), START)
        edited = entry.edited(draft(slug="vizzion-2"), START + timedelta(hours=1))
        assert (edited.version, edited.slug, edited.updated_at) == (
            2,
            "vizzion-2",
            START + timedelta(hours=1),
        )

    def test_publish_needs_every_language(self) -> None:
        only_en = draft(translations={Lang.EN: Translation.create("T", "S")})
        with pytest.raises(IncompleteEntryError, match="pt"):
            Entry.new(uuid4(), Kind.EXPERIENCE, only_en, START).published(START)
        empty_pt = draft(translations={**BOTH, Lang.PT: Translation.create("Título")})
        with pytest.raises(IncompleteEntryError):
            Entry.new(uuid4(), Kind.EXPERIENCE, empty_pt, START).published(START)
        body_only = draft(translations={**BOTH, Lang.PT: Translation.create("T", "", BODY)})
        assert Entry.new(uuid4(), Kind.EXPERIENCE, body_only, START).published(START).version == 2

    def test_a_title_is_always_required(self) -> None:
        untitled = {**BOTH, Lang.PT: Translation.create("", "Resumo")}
        entry = Entry.new(uuid4(), Kind.EXPERIENCE, draft(translations=untitled), START)
        with pytest.raises(IncompleteEntryError):
            entry.published(START)

    def test_a_skill_only_needs_titles(self) -> None:
        titles = {Lang.EN: Translation.create("Python"), Lang.PT: Translation.create("Python")}
        skill = Entry.new(uuid4(), Kind.SKILL, draft(Kind.SKILL, translations=titles), START)
        assert skill.published(START).status is Status.PUBLISHED

    def test_first_publication_date_is_kept(self) -> None:
        entry = Entry.new(uuid4(), Kind.EXPERIENCE, draft(), START).published(START)
        later = START + timedelta(days=3)
        again = entry.unpublished(later).published(later)
        assert (again.published_at, again.version, again.status) == (START, 4, Status.PUBLISHED)


class TestAvailabilityStamp:
    def _profile(self, availability: str) -> EntryDraft:
        return EntryDraft.build(
            Kind.PROFILE,
            slug="erick",
            translations=BOTH,
            details={"name": "Erick", "availability": availability},
        )

    def test_set_on_creation(self) -> None:
        entry = Entry.new(uuid4(), Kind.PROFILE, self._profile("open"), START)
        assert entry.content.details["availability_updated_at"] == "2026-11-02"

    def test_kept_when_unchanged_and_updated_when_changed(self) -> None:
        entry = Entry.new(uuid4(), Kind.PROFILE, self._profile("open"), START)
        same = entry.edited(self._profile("open"), START + timedelta(days=5))
        assert same.content.details["availability_updated_at"] == "2026-11-02"
        changed = same.edited(self._profile("not_looking"), START + timedelta(days=9))
        assert changed.content.details["availability_updated_at"] == "2026-11-11"

    def test_other_kinds_are_untouched(self) -> None:
        entry = Entry.new(uuid4(), Kind.EXPERIENCE, draft(), START)
        assert "availability_updated_at" not in entry.content.details


def test_events_and_errors() -> None:
    entry = Entry.new(uuid4(), Kind.EXPERIENCE, draft(), START)
    assert entry_published(entry).payload == {
        "id": str(entry.id),
        "kind": "experience",
        "slug": "vizzion",
        "version": 1,
    }
    assert entry_deleted(entry.id).topic == "content.entry.deleted"
    assert VersionConflictError(3).current == 3
    assert str(entry.id) in str(EntryNotFoundError(entry.id))
