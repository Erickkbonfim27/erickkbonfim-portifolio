from dataclasses import replace
from pathlib import Path

import pytest

from portfolio import cli
from portfolio.contexts.content.domain import richtext
from portfolio.contexts.content.domain.entry import Attachment
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status
from portfolio.contexts.content.interfaces.seed import (
    SeedError,
    inline,
    markdown_to_doc,
    read_entries,
    seed,
)
from tests.unit.files.test_files import PDF
from tests.unit.support import World, make_world

SKILLS = """
[[entry]]
kind = "skill"
slug = "python"
details = { category = "language" }
en = { title = "Python" }
pt = { title = "Python" }
"""

PROJECT = """
[[entry]]
kind = "project"
slug = "rhye"
position = 10
tags = ["Agents", "rag"]
skills = ["python"]
details = { collection = "portfolio", state = "active" }
en = { title = "Rhye", summary = "AI platform.", body = '''
## Problem
Sales teams **guess**.
'''}
pt = { title = "Rhye", summary = "Plataforma de IA." }
"""

PROFILE = """
[[entry]]
kind = "profile"
slug = "profile"
details = { name = "Erick", availability = "open" }
en = { title = "AI Engineer", summary = "Builds agents." }
pt = { title = "Engenheiro de IA", summary = "Constrói agentes." }
"""


def write(directory: Path, **files: str) -> Path:
    for name, text in files.items():
        (directory / f"{name}.toml").write_text(text, encoding="utf-8")
    return directory


class TestMarkdown:
    def test_blocks(self) -> None:
        doc = markdown_to_doc(
            """
## Problem
First line
continues here.

> A quote
> on two lines.

- one
- **two**

1. first
2. second

#### Small

```python
print("hi")
```

```
plain
```
"""
        )
        assert richtext.validate(doc) == doc
        assert [b["type"] for b in doc["content"]] == [
            "heading",
            "paragraph",
            "blockquote",
            "bulletList",
            "orderedList",
            "heading",
            "codeBlock",
            "codeBlock",
        ]
        heading, paragraph, quote, bullets, numbered, small, code, plain = doc["content"]
        assert heading["attrs"] == {"level": 2}
        assert small["attrs"] == {"level": 4}
        assert paragraph["content"] == [{"type": "text", "text": "First line continues here."}]
        assert quote["content"][0]["content"][0]["text"] == "A quote on two lines."
        assert len(bullets["content"]) == 2
        assert numbered["content"][1]["content"][0]["content"][0]["text"] == "second"
        assert code == {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [{"type": "text", "text": 'print("hi")'}],
        }
        assert "attrs" not in plain

    def test_a_paragraph_stops_where_another_block_starts(self) -> None:
        doc = markdown_to_doc("Intro\n## Heading\ntext\n- item\nafter\n> quote")
        assert [b["type"] for b in doc["content"]] == [
            "paragraph",
            "heading",
            "paragraph",
            "bulletList",
            "paragraph",
            "blockquote",
        ]

    def test_inline_marks_and_links(self) -> None:
        assert inline("a **b** *c* `d` [e](https://e.dev) f") == [
            {"type": "text", "text": "a "},
            {"type": "text", "text": "b", "marks": [{"type": "bold"}]},
            {"type": "text", "text": " "},
            {"type": "text", "text": "c", "marks": [{"type": "italic"}]},
            {"type": "text", "text": " "},
            {"type": "text", "text": "d", "marks": [{"type": "code"}]},
            {"type": "text", "text": " "},
            {
                "type": "text",
                "text": "e",
                "marks": [{"type": "link", "attrs": {"href": "https://e.dev"}}],
            },
            {"type": "text", "text": " f"},
        ]

    def test_plain_asterisks_stay_text(self) -> None:
        assert inline("2 * 3 * 4") == [{"type": "text", "text": "2 * 3 * 4"}]


class TestFiles:
    def test_reads_a_directory_with_skills_first(self, tmp_path: Path) -> None:
        write(tmp_path, a_project=PROJECT, b_skills=SKILLS)
        entries = read_entries([tmp_path])
        assert [e.label for e in entries] == ["skill/python", "project/rhye"]

    def test_reads_single_files(self, tmp_path: Path) -> None:
        write(tmp_path, skills=SKILLS)
        assert [e.slug for e in read_entries([tmp_path / "skills.toml"])] == ["python"]

    @pytest.mark.parametrize(
        ("files", "reason"),
        [
            ({"a": SKILLS, "b": SKILLS}, "appears twice"),
            ({"a": '[[entry]]\nkind = "nope"\nslug = "x"\n'}, "valid kind and slug"),
            ({"a": '[[entry]]\nkind = "skill"\n'}, "valid kind and slug"),
            ({"a": "not = [toml"}, "a.toml"),
            ({"a": 'title = "no entries"'}, "no \\[\\[entry\\]\\] found"),
        ],
    )
    def test_refuses(self, tmp_path: Path, files: dict[str, str], reason: str) -> None:
        write(tmp_path, **files)
        with pytest.raises(SeedError, match=reason):
            read_entries([tmp_path])


async def run(world: World, directory: Path) -> tuple[int, list[str]]:
    said: list[str] = []
    code = await seed(world.container().content, [directory], said.append)
    return code, said


class TestSeed:
    async def test_creates_and_publishes_everything(self, tmp_path: Path) -> None:
        world = make_world()
        code, said = await run(world, write(tmp_path, skills=SKILLS, project=PROJECT, me=PROFILE))
        assert (code, said[-1]) == (
            0,
            "Seed applied: 3 created, 0 updated, 0 unchanged, 3 published.",
        )
        entries = {e.slug: e for e in await world.container().content.list()}
        assert all(e.status is Status.PUBLISHED for e in entries.values())
        rhye = entries["rhye"]
        assert rhye.content.skills == (entries["python"].id,)
        assert rhye.content.tags == ("agents", "rag")
        assert rhye.content.position == 10
        assert (
            richtext.plain_text(rhye.content.translations[Lang.EN].body)
            == "Problem\nSales teams guess."
        )
        assert entries["profile"].content.details["availability_updated_at"]

    async def test_running_again_changes_nothing(self, tmp_path: Path) -> None:
        world = make_world()
        directory = write(tmp_path, skills=SKILLS, project=PROJECT, me=PROFILE)
        await run(world, directory)
        before = {e.slug: e.version for e in await world.container().content.list()}
        code, said = await run(world, directory)
        assert (code, said[-1]) == (
            0,
            "Seed applied: 0 created, 0 updated, 3 unchanged, 0 published.",
        )
        assert {e.slug: e.version for e in await world.container().content.list()} == before

    async def test_updates_what_changed_and_keeps_attachments(self, tmp_path: Path) -> None:
        world = make_world()
        directory = write(tmp_path, skills=SKILLS, project=PROJECT)
        await run(world, directory)
        container = world.container()
        rhye = next(e for e in await container.content.list(Kind.PROJECT))
        deck = (await container.files.upload("deck.pdf", PDF)).file
        with_deck = replace(rhye.content, attachments=(Attachment(deck.id, "Deck"),))
        await container.content.update(rhye.id, rhye.version, with_deck)

        write(tmp_path, project=PROJECT.replace("AI platform.", "An AI platform."))
        code, said = await run(world, directory)
        assert said[-1] == "Seed applied: 0 created, 1 updated, 1 unchanged, 0 published."
        rhye = next(e for e in await container.content.list(Kind.PROJECT))
        assert rhye.content.translations[Lang.EN].summary == "An AI platform."
        assert rhye.content.attachments == (Attachment(deck.id, "Deck"),)
        assert code == 0

    async def test_publishes_an_existing_draft(self, tmp_path: Path) -> None:
        world = make_world()
        directory = write(tmp_path, skills=SKILLS)
        await run(world, directory)
        content = world.container().content
        [python] = await content.list(Kind.SKILL)
        await content.unpublish(python.id, python.version)
        _, said = await run(world, directory)
        assert said[-1] == "Seed applied: 0 created, 0 updated, 1 unchanged, 1 published."

    async def test_reports_entries_missing_from_the_files(self, tmp_path: Path) -> None:
        world = make_world()
        await run(world, write(tmp_path, skills=SKILLS, project=PROJECT))
        (tmp_path / "project.toml").unlink()
        _, said = await run(world, tmp_path)
        assert "Not in the seed files (left as is): project/rhye" in said

    @pytest.mark.parametrize(
        ("files", "reason"),
        [
            ({"project": PROJECT}, "Seed stopped at project/rhye: project/rhye: unknown skills"),
            (
                {
                    "me": PROFILE.replace(
                        'pt = { title = "Engenheiro de IA", summary = "Constrói agentes." }', ""
                    )
                },
                "Seed stopped at profile/profile: fill in every language",
            ),
            ({"bad": "not = [toml"}, "Seed refused: bad.toml"),
        ],
    )
    async def test_stops_with_the_reason(
        self, tmp_path: Path, files: dict[str, str], reason: str
    ) -> None:
        code, said = await run(make_world(), write(tmp_path, **files))
        assert code == 1
        assert said[-1].startswith(reason)


def test_cli_seed_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    world = make_world()
    write(tmp_path, skills=SKILLS)
    assert cli.main(["seed", str(tmp_path)], container=world.container()) == 0
    assert "1 created" in capsys.readouterr().out
