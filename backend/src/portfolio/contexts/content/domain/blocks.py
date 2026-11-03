"""Structured blocks inside rich text: galleries, diagrams, logo walls, metrics…

A block is a leaf node `{"type": "block", "attrs": {"kind", "data", "hidden"}}`
at the top level of a document. Its `data` is validated here against a small
schema per kind, like the details of an entry: unknown keys are rejected, text
has a length limit, links must be http(s). The site renders each kind with its
own component; everything else (search, MCP, plain HTML) reads the text that
`block_text` extracts.

`hidden` keeps a block in the document without publishing it: a hidden block
never leaves the server, in any representation.

A `note` is the one kind that is never drawn on a page: something Erick wants the
site's agent to be able to say when asked (why he left a job), indexed for search
but absent from the page, the API's body and the MCP.
"""

import re
from collections.abc import Callable, Mapping
from html import escape
from typing import Any
from urllib.parse import urlparse

from portfolio.contexts.content.domain.errors import InvalidRichTextError

MAX_URL = 2000
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,19}$")
MAX_CANVAS = 4000
MAX_LOGOS = 400

Data = Mapping[str, Any]
Check = Callable[[object, str], Any]


def _fail(path: str, reason: str) -> InvalidRichTextError:
    return InvalidRichTextError(f"{path}: {reason}")


# --- field checks -------------------------------------------------------------


def text(max_length: int) -> Check:
    def check(value: object, path: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise _fail(path, f"must be text up to {max_length} characters")
        return value.strip()

    return check


def url(value: object, path: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_URL:
        raise _fail(path, "must be a URL")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise _fail(path, "must be an http(s) URL")
    return value


def flag(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(path, "must be true or false")
    return value


def number(low: float, high: float) -> Check:
    def check(value: object, path: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not low <= value <= high
        ):
            raise _fail(path, f"must be a number from {low} to {high}")
        return value

    return check


def choice(*options: str) -> Check:
    def check(value: object, path: str) -> str:
        if value not in options:
            raise _fail(path, f"must be one of {list(options)}")
        return str(value)

    return check


def pattern(regex: re.Pattern[str], what: str) -> Check:
    def check(value: object, path: str) -> str:
        if not isinstance(value, str) or not regex.match(value):
            raise _fail(path, f"must be {what}")
        return value

    return check


def record(required: Mapping[str, Check], optional: Mapping[str, Check] | None = None) -> Check:
    optional = optional or {}

    def check(value: object, path: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise _fail(path, "must be an object")
        unknown = set(value) - set(required) - set(optional)
        if unknown:
            raise _fail(path, f"unknown fields {sorted(unknown)}")
        parsed: dict[str, Any] = {}
        for name, field in required.items():
            if value.get(name) is None:
                raise _fail(path, f"{name} is required")
            parsed[name] = field(value[name], f"{path}.{name}")
        for name, field in optional.items():
            if value.get(name) is not None:
                parsed[name] = field(value[name], f"{path}.{name}")
        return parsed

    return check


def items(item: Check, low: int, high: int) -> Check:
    def check(value: object, path: str) -> list[Any]:
        if not isinstance(value, list) or not low <= len(value) <= high:
            raise _fail(path, f"must be a list of {low} to {high}")
        return [item(element, f"{path}[{index}]") for index, element in enumerate(value)]

    return check


_IMAGE = record({"src": text(MAX_URL), "alt": text(200)})
_LINK = record({"label": text(60), "url": url})
_TONE = choice("default", "accent", "muted")
_DIAGRAM_ID = pattern(_ID, "a lowercase id")


def _diagram(value: object, path: str) -> dict[str, Any]:
    coordinate = number(0, MAX_CANVAS)
    parsed: dict[str, Any] = record(
        {
            "width": number(100, MAX_CANVAS),
            "height": number(100, MAX_CANVAS),
            "nodes": items(
                record(
                    {"id": _DIAGRAM_ID, "label": text(60), "x": coordinate, "y": coordinate},
                    {"sub": text(80), "w": coordinate, "h": coordinate, "tone": _TONE},
                ),
                1,
                60,
            ),
        },
        {
            "title": text(120),
            "groups": items(
                record(
                    {
                        "id": _DIAGRAM_ID,
                        "label": text(60),
                        "x": coordinate,
                        "y": coordinate,
                        "w": coordinate,
                        "h": coordinate,
                    },
                    {"tone": _TONE},
                ),
                0,
                20,
            ),
            "edges": items(
                record(
                    {"from": _DIAGRAM_ID, "to": _DIAGRAM_ID},
                    {"label": text(40), "dashed": flag, "flow": flag},
                ),
                0,
                120,
            ),
            "steps": items(
                record(
                    {"title": text(80), "text": text(600)},
                    {"focus": items(_DIAGRAM_ID, 0, 60)},
                ),
                0,
                12,
            ),
        },
    )(value, path)
    nodes = [node["id"] for node in parsed["nodes"]]
    groups = [group["id"] for group in parsed.get("groups", [])]
    if len(set(nodes + groups)) != len(nodes) + len(groups):
        raise _fail(path, "node and group ids must be unique")
    for index, edge in enumerate(parsed.get("edges", [])):
        if edge["from"] not in nodes or edge["to"] not in nodes:
            raise _fail(f"{path}.edges[{index}]", "edges must join existing nodes")
    known = set(nodes + groups)
    for index, step in enumerate(parsed.get("steps", [])):
        if not set(step.get("focus", [])) <= known:
            raise _fail(f"{path}.steps[{index}]", "focus must name nodes or groups")
    return parsed


def _logos(value: object, path: str) -> dict[str, Any]:
    logo = record({"name": text(80)}, {"logo": text(MAX_URL), "url": url, "note": text(80)})
    parsed: dict[str, Any] = record(
        {"groups": items(record({"title": text(80), "items": items(logo, 1, MAX_LOGOS)}), 1, 30)},
        {"title": text(120), "note": text(400)},
    )(value, path)
    if sum(len(group["items"]) for group in parsed["groups"]) > MAX_LOGOS:
        raise _fail(path, f"at most {MAX_LOGOS} logos per block")
    return parsed


SCHEMAS: dict[str, Check] = {
    "facts": record({"items": items(record({"label": text(40), "text": text(400)}), 1, 4)}),
    "metrics": record(
        {"items": items(record({"value": text(24), "label": text(80)}, {"note": text(160)}), 1, 6)}
    ),
    "gallery": record(
        {
            "items": items(
                record(
                    {"src": text(MAX_URL), "alt": text(200)},
                    {"caption": text(280), "wide": flag},
                ),
                1,
                30,
            )
        },
        {"layout": choice("grid", "strip", "feature")},
    ),
    "timeline": record(
        {
            "items": items(
                record(
                    {"when": text(40), "title": text(120)},
                    {
                        "text": text(600),
                        "place": text(80),
                        "tag": text(40),
                        "image": _IMAGE,
                        "link": _LINK,
                    },
                ),
                1,
                40,
            )
        },
        {"style": choice("list", "roadbook"), "title": text(120)},
    ),
    "diagram": _diagram,
    "logos": _logos,
    "cases": record(
        {
            "items": items(
                record(
                    {
                        "title": text(120),
                        "parts": items(record({"label": text(40), "text": text(900)}), 1, 6),
                    },
                    {"tag": text(40)},
                ),
                1,
                12,
            )
        }
    ),
    "note": record({"text": text(600)}),
    "quote": record({"text": text(600), "author": text(80)}, {"role": text(120), "url": url}),
    "map": record(
        {
            "src": text(MAX_URL),
            "attribution": text(160),
            "metrics": items(
                record(
                    {"key": pattern(_KEY, "a lowercase key"), "label": text(40)},
                    # What the measure means, and how to read its two ends.
                    {"note": text(300), "low": text(40), "high": text(40)},
                ),
                1,
                4,
            ),
        },
        {"caption": text(400), "legend": record({"low": text(40), "high": text(40)})},
    ),
}

KINDS = frozenset(SCHEMAS)


def validate_block(attrs: Mapping[str, Any], path: str) -> None:
    kind = attrs.get("kind")
    if kind not in SCHEMAS:
        raise _fail(path, f"block kind must be one of {sorted(SCHEMAS)}")
    if attrs.get("hidden") is not None:
        flag(attrs["hidden"], f"{path}.hidden")
    SCHEMAS[kind](attrs.get("data"), f"{path}.data")


def is_visible(attrs: Mapping[str, Any]) -> bool:
    return attrs.get("hidden") is not True


# --- what leaves the server ---------------------------------------------------


def public_data(kind: str, data: Data, own: Callable[[str], bool]) -> dict[str, Any] | None:
    """The block as the site receives it: images that are not ours are removed.

    Returns None when nothing is left to show (a map whose layer is foreign).
    """
    if kind == "note":
        return None
    clean: dict[str, Any] = dict(data)
    if kind == "gallery":
        clean["items"] = [item for item in data["items"] if own(item["src"])]
        return clean if clean["items"] else None
    if kind == "timeline":
        clean["items"] = [
            item if "image" not in item or own(item["image"]["src"]) else _without(item, "image")
            for item in data["items"]
        ]
    elif kind == "logos":
        clean["groups"] = [
            {
                **group,
                "items": [
                    item if "logo" not in item or own(item["logo"]) else _without(item, "logo")
                    for item in group["items"]
                ],
            }
            for group in data["groups"]
        ]
    elif kind == "map" and not own(data["src"]):
        return None
    return clean


def _without(item: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in item.items() if name != key}


# Not words a reader would search for. Alt text is left out too: it describes a photo
# for screen readers, and captions already say what the photo is about.
_NOT_TEXT = frozenset({"src", "logo", "url", "key", "layout", "style", "alt", "image"})


def block_text(kind: str, data: Data) -> str:
    """The words of a block, one item per line, for search and plain-text readers."""
    if kind == "diagram":
        lines = [data.get("title", "")]
        lines += [f"{node['label']}: {node.get('sub', '')}" for node in data["nodes"]]
        lines += [f"{step['title']}: {step['text']}" for step in data.get("steps", [])]
        return "\n".join(line.strip(": ") for line in lines if line.strip(": "))
    if kind == "metrics":
        # Read as a sentence: "54 pull requests em 6,5 semanas (mai a out de 2026)".
        return "\n".join(
            f"{item['value']} {item['label']}" + (f" ({item['note']})" if item.get("note") else "")
            for item in data["items"]
        )

    def walk(value: object) -> list[str]:
        if isinstance(value, Mapping):
            words = [
                text for key, field in value.items() if key not in _NOT_TEXT for text in walk(field)
            ]
            return [" · ".join(words)] if words else []
        if isinstance(value, list):
            return [line for element in value for line in walk(element)]
        return [value] if isinstance(value, str) else []

    lines = [line for key, field in data.items() if key not in _NOT_TEXT for line in walk(field)]
    return "\n".join(lines)


def block_html(kind: str, data: Data) -> str:
    """A plain HTML fallback, for readers without the site's components."""
    if kind == "gallery":
        figures = "".join(
            f'<figure><img src="{escape(item["src"])}" alt="{escape(item["alt"])}" '
            f'loading="lazy">'
            + (f"<figcaption>{escape(item['caption'])}</figcaption>" if "caption" in item else "")
            + "</figure>"
            for item in data["items"]
        )
        return f'<div class="block block-gallery">{figures}</div>'
    if kind == "quote":
        cite = escape(data["author"]) + (f", {escape(data['role'])}" if "role" in data else "")
        return f"<blockquote><p>{escape(data['text'])}</p><footer>{cite}</footer></blockquote>"
    lines = "".join(f"<li>{escape(line)}</li>" for line in block_text(kind, data).splitlines())
    return f'<ul class="block block-{kind}">{lines}</ul>'
