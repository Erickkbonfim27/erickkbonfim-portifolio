"""`portfolio seed PATH`: publish content written as TOML files.

Another inbound adapter over the same use cases as the admin API, so every rule
(validation, both languages before publishing, outbox events that reindex search)
applies unchanged. The files live outside the public repository.

Idempotent: entries are matched by kind and slug. A new one is created and
published, a changed one is updated, an unchanged one is left alone. Entries that
are in the database but not in the files are reported, never deleted.

    [[entry]]
    kind = "project"
    slug = "rhye"
    position = 10
    tags = ["agents", "rag"]
    skills = ["python", "langgraph"]        # skill slugs, seeded in the same run
    details = { collection = "portfolio", state = "active" }
    en = { title = "Rhye", summary = "…", body = '''
    ## Problem
    Markdown: ## to #### headings, - and 1. lists, > quotes, ``` code,
    **bold**, *italic*, `code` and [links](https://…).
    ''' }
    pt = { title = "Rhye", summary = "…" }

`draft = true` keeps an entry in the database without publishing it (a case
that waits for its results). An entry that is already published stays published.

Structured blocks (domain/blocks.py) are fenced JSON, optionally `hidden`. A
string `"file:<path>"` anywhere in a body is a local file, relative to the seed
directory: it is uploaded (photos become WebP without metadata, and the same
bytes are stored once) and replaced by its public URL.

    ```block gallery
    {"layout": "feature", "items": [{"src": "file:photos/booth.heic", "alt": "…"}]}
    ```

A line `@include <path>` is replaced by that file's text, for blocks too large to
write inline (a wall of 150 logos).
"""

import json
import re
import tomllib
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from portfolio.contexts.content.application.use_cases import ContentUseCases
from portfolio.contexts.content.domain.details import SERVER_MANAGED
from portfolio.contexts.content.domain.entry import Entry, EntryDraft, Translation
from portfolio.contexts.content.domain.errors import ContentError
from portfolio.contexts.content.domain.kinds import Kind, Lang, Status

Say = Callable[[str], None]
Upload = Callable[[Path], Awaitable[str]]

# --- Markdown subset to the canonical rich-text document -----------------------

_INLINE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*"
    r"|(?<![\w*])\*(?P<italic>[^*\s](?:[^*]*[^*\s])?)\*"
    r"|`(?P<code>[^`]+)`"
    r"|\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)\)"
)
_HEADING = re.compile(r"^(#{2,4})\s+(.*)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED = re.compile(r"^\d+[.)]\s+(.*)$")


def _text(value: str, marks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": value}
    if marks:
        node["marks"] = marks
    return node


def inline(source: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    cursor = 0
    for match in _INLINE.finditer(source):
        if match.start() > cursor:
            nodes.append(_text(source[cursor : match.start()]))
        if match["bold"] is not None:
            nodes.append(_text(match["bold"], [{"type": "bold"}]))
        elif match["italic"] is not None:
            nodes.append(_text(match["italic"], [{"type": "italic"}]))
        elif match["code"] is not None:
            nodes.append(_text(match["code"], [{"type": "code"}]))
        else:
            link = {"type": "link", "attrs": {"href": match["href"]}}
            nodes.append(_text(match["label"], [link]))
        cursor = match.end()
    if cursor < len(source):
        nodes.append(_text(source[cursor:]))
    return nodes


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": inline(text)}


def _list(kind: str, items: Sequence[str]) -> dict[str, Any]:
    return {
        "type": kind,
        "content": [{"type": "listItem", "content": [_paragraph(item)]} for item in items],
    }


def _block(info: str, source: str) -> dict[str, Any]:
    _, *words = info.split()
    if not words or words[1:] not in ([], ["hidden"]):
        raise SeedError("a block fence is ```block <kind> [hidden]")
    try:
        data = json.loads(source)
    except ValueError as error:
        raise SeedError(f"block {words[0]}: invalid JSON ({error})") from error
    attrs: dict[str, Any] = {"kind": words[0], "data": data}
    if words[1:]:
        attrs["hidden"] = True
    return {"type": "block", "attrs": attrs}


def _fenced(info: str, source: str) -> dict[str, Any]:
    if info.split(maxsplit=1)[:1] == ["block"]:
        return _block(info, source)
    code: dict[str, Any] = {"type": "codeBlock", "content": [_text(source)]}
    if info:
        code["attrs"] = {"language": info}
    return code


def markdown_to_doc(source: str) -> dict[str, Any]:
    """Blocks are separated by blank lines; lines of one paragraph are joined."""
    blocks: list[dict[str, Any]] = []
    lines = source.strip("\n").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
        elif line.startswith("```"):
            info = line[3:].strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # the closing fence
            blocks.append(_fenced(info, "\n".join(body)))
        elif heading := _HEADING.match(line):
            level = len(heading[1])
            blocks.append(
                {"type": "heading", "attrs": {"level": level}, "content": inline(heading[2])}
            )
            i += 1
        elif _BULLET.match(line) or _NUMBERED.match(line):
            pattern, kind = (
                (_BULLET, "bulletList")
                if _BULLET.match(line)
                else (
                    _NUMBERED,
                    "orderedList",
                )
            )
            items: list[str] = []
            while i < len(lines) and (item := pattern.match(lines[i].strip())):
                items.append(item[1])
                i += 1
            blocks.append(_list(kind, items))
        else:
            quote = line.startswith(">")
            paragraph: list[str] = []
            while i < len(lines) and (current := lines[i].strip()):
                if current.startswith(("```", "#")) or _BULLET.match(current):
                    break
                if quote != current.startswith(">"):
                    break
                paragraph.append(current.removeprefix(">").strip() if quote else current)
                i += 1
            block = _paragraph(" ".join(paragraph))
            blocks.append({"type": "blockquote", "content": [block]} if quote else block)
    return {"type": "doc", "content": blocks}


# --- seed files ----------------------------------------------------------------


class SeedError(Exception):
    """A seed file that cannot be applied; the message names the entry."""


@dataclass(frozen=True, slots=True)
class SeedEntry:
    kind: Kind
    slug: str
    raw: Mapping[str, Any]
    base: Path = Path()  # the directory "file:" paths are relative to

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.slug}"


def read_entries(paths: Iterable[Path]) -> list[SeedEntry]:
    """Every [[entry]] of the given files, or of the *.toml files in a directory."""
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.glob("*.toml")) if path.is_dir() else [path])
    entries: list[SeedEntry] = []
    seen: set[tuple[Kind, str]] = set()
    for file in files:
        try:
            data = tomllib.loads(file.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise SeedError(f"{file.name}: {error}") from error
        for raw in data.get("entry", []):
            try:
                kind, slug = Kind(raw["kind"]), str(raw["slug"])
            except (KeyError, ValueError) as error:
                raise SeedError(f"{file.name}: every entry needs a valid kind and slug") from error
            if (kind, slug) in seen:
                raise SeedError(f"{file.name}: {kind}/{slug} appears twice")
            seen.add((kind, slug))
            entries.append(SeedEntry(kind, slug, raw, file.parent))
    if not entries:
        raise SeedError("no [[entry]] found")
    # Skills first: other entries refer to them.
    return sorted(entries, key=lambda e: e.kind is not Kind.SKILL)


_FILE = re.compile(r'"file:([^"]+)"')
_INCLUDE = re.compile(r"^@include (\S+)$", re.MULTILINE)


def _include(entry: SeedEntry, body: str) -> str:
    def text(match: re.Match[str]) -> str:
        path = entry.base / match[1]
        if not path.is_file():
            raise SeedError(f"{entry.label}: no such file to include {match[1]}")
        return path.read_text(encoding="utf-8")

    return _INCLUDE.sub(text, body)


async def upload_files(entries: Sequence[SeedEntry], upload: Upload | None) -> list[SeedEntry]:
    """Replace every "file:<path>" in the bodies by the URL of the uploaded file."""
    urls: dict[Path, str] = {}

    async def resolve(entry: SeedEntry, body: str) -> str:
        body = _include(entry, body)
        out, cursor = [], 0
        for match in _FILE.finditer(body):
            path = (entry.base / match[1]).resolve()
            if path not in urls:
                if upload is None:
                    raise SeedError(f"{entry.label}: files need storage to upload {match[1]}")
                if not path.is_file():
                    raise SeedError(f"{entry.label}: no such file {match[1]}")
                urls[path] = await upload(path)
            out += [body[cursor : match.start()], json.dumps(urls[path])]
            cursor = match.end()
        return "".join([*out, body[cursor:]])

    resolved = []
    for entry in entries:
        raw = dict(entry.raw)
        for lang in Lang:
            text = raw.get(lang.value)
            if isinstance(text, Mapping) and isinstance(text.get("body"), str):
                raw[lang.value] = {**text, "body": await resolve(entry, text["body"])}
        resolved.append(replace(entry, raw=raw))
    return resolved


def _translation(raw: Mapping[str, Any]) -> Translation:
    body = raw.get("body")
    return Translation.create(
        str(raw.get("title", "")),
        str(raw.get("summary", "")),
        markdown_to_doc(body) if isinstance(body, str) else None,
    )


def build_draft(entry: SeedEntry, skill_ids: Mapping[str, UUID]) -> EntryDraft:
    raw = entry.raw
    unknown = [s for s in raw.get("skills", []) if s not in skill_ids]
    if unknown:
        raise SeedError(f"{entry.label}: unknown skills {unknown}")
    return EntryDraft.build(
        entry.kind,
        slug=entry.slug,
        translations={lang: _translation(raw[lang.value]) for lang in Lang if lang.value in raw},
        details=raw.get("details", {}),
        tags=raw.get("tags", []),
        skills=[skill_ids[s] for s in raw.get("skills", [])],
        position=int(raw.get("position", 0)),
    )


def _same(current: EntryDraft, draft: EntryDraft) -> bool:
    """Equal content, ignoring what the domain stamps itself."""
    kept = {k: v for k, v in current.details.items() if k not in SERVER_MANAGED}
    return replace(current, details=kept) == replace(draft, details=dict(draft.details))


@dataclass
class SeedReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    published: int = 0


async def _apply(
    content: ContentUseCases,
    existing: Entry | None,
    entry: SeedEntry,
    draft: EntryDraft,
    report: SeedReport,
) -> Entry:
    if existing is not None and not draft.attachments:
        # Files are attached in the admin; the seed never detaches them.
        draft = replace(draft, attachments=existing.content.attachments)
    if existing is None:
        current = await content.create(entry.kind, draft)
        report.created += 1
    elif _same(existing.content, draft):
        current = existing
        report.unchanged += 1
    else:
        current = await content.update(existing.id, existing.version, draft)
        report.updated += 1
    if current.status is Status.DRAFT and not entry.raw.get("draft", False):
        current = await content.publish(current.id, current.version)
        report.published += 1
    return current


async def seed(
    content: ContentUseCases, paths: Sequence[Path], say: Say, upload: Upload | None = None
) -> int:
    try:
        entries = await upload_files(read_entries(paths), upload)
    except SeedError as error:
        say(f"Seed refused: {error}")
        return 1
    in_database = {(e.kind, e.slug): e for e in await content.list()}
    skill_ids = {slug: e.id for (kind, slug), e in in_database.items() if kind is Kind.SKILL}
    report = SeedReport()
    for entry in entries:
        try:
            draft = build_draft(entry, skill_ids)
            current = await _apply(
                content, in_database.get((entry.kind, entry.slug)), entry, draft, report
            )
        except (SeedError, ContentError) as error:
            say(f"Seed stopped at {entry.label}: {error}")
            return 1
        if entry.kind is Kind.SKILL:
            skill_ids[entry.slug] = current.id
    listed = {(e.kind, e.slug) for e in entries}
    for key in sorted(set(in_database) - listed):
        say(f"Not in the seed files (left as is): {key[0]}/{key[1]}")
    say(
        f"Seed applied: {report.created} created, {report.updated} updated, "
        f"{report.unchanged} unchanged, {report.published} published."
    )
    return 0
