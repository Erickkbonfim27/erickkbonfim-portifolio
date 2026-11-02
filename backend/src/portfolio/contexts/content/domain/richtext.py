"""TipTap (ProseMirror) JSON: validation and HTML rendering.

The JSON document is the canonical form. HTML is derived here, on the server, from
an allow-list of nodes, marks and attributes, and every piece of text is escaped.
Anything outside the allow-list is rejected, not silently dropped, so the editor
and the server can never disagree about what was saved.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html import escape
from typing import Any
from urllib.parse import urlparse

from portfolio.contexts.content.domain.errors import InvalidRichTextError

MAX_NODES = 5000
MAX_DEPTH = 24
MAX_TEXT = 200_000
HEADING_LEVELS = frozenset({2, 3, 4})  # h1 belongs to the page title
TEXT_ALIGN = frozenset({"left", "center", "right", "justify"})
CODE_LANGUAGE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789+#-_")
LINK_SCHEMES = frozenset({"http", "https", "mailto"})
MAX_URL = 2000
MAX_LIST_START = 10_000
MAX_SPAN = 50

EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": []}

Node = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Images may only point at our own file storage, never at a third party."""

    image_base_url: str


# --- validation ---------------------------------------------------------------

_BLOCK_CHILDREN = frozenset(
    {
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "blockquote",
        "codeBlock",
        "horizontalRule",
        "image",
        "table",
    }
)
_INLINE = frozenset({"text", "hardBreak"})

# node type -> (allowed child types or None for leaf, allowed attribute names)
_NODES: dict[str, tuple[frozenset[str] | None, frozenset[str]]] = {
    "doc": (_BLOCK_CHILDREN, frozenset()),
    "paragraph": (_INLINE, frozenset({"textAlign"})),
    "heading": (_INLINE, frozenset({"level", "textAlign"})),
    "bulletList": (frozenset({"listItem"}), frozenset()),
    "orderedList": (frozenset({"listItem"}), frozenset({"start", "type"})),
    "listItem": (_BLOCK_CHILDREN, frozenset()),
    "blockquote": (_BLOCK_CHILDREN, frozenset()),
    "codeBlock": (frozenset({"text"}), frozenset({"language"})),
    "horizontalRule": (None, frozenset()),
    "image": (None, frozenset({"src", "alt", "title"})),
    "table": (frozenset({"tableRow"}), frozenset()),
    "tableRow": (frozenset({"tableHeader", "tableCell"}), frozenset()),
    "tableHeader": (_BLOCK_CHILDREN, frozenset({"colspan", "rowspan", "colwidth"})),
    "tableCell": (_BLOCK_CHILDREN, frozenset({"colspan", "rowspan", "colwidth"})),
    "text": (None, frozenset()),
    "hardBreak": (None, frozenset()),
}

_MARKS: dict[str, frozenset[str]] = {
    "bold": frozenset(),
    "italic": frozenset(),
    "underline": frozenset(),
    "strike": frozenset(),
    "code": frozenset(),
    "highlight": frozenset(),
    "subscript": frozenset(),
    "superscript": frozenset(),
    "link": frozenset({"href", "target", "rel", "class"}),
}


def _fail(path: str, reason: str) -> InvalidRichTextError:
    return InvalidRichTextError(f"{path}: {reason}")


def safe_link(href: object) -> str | None:
    if not isinstance(href, str) or len(href) > MAX_URL:
        return None
    scheme = urlparse(href.strip()).scheme.lower()
    return href.strip() if scheme in LINK_SCHEMES else None


def _attrs(node: Node, allowed: frozenset[str], path: str) -> Mapping[str, Any]:
    attrs = node.get("attrs")
    if attrs is None:
        return {}
    if not isinstance(attrs, Mapping):
        raise _fail(path, "attrs must be an object")
    # TipTap emits every attribute with null defaults; only non-null ones must be known.
    unknown = {key for key, value in attrs.items() if value is not None} - allowed
    if unknown:
        raise _fail(path, f"unknown attributes {sorted(unknown)}")
    return attrs


def _check_attrs(kind: str, attrs: Mapping[str, Any], path: str) -> None:
    align = attrs.get("textAlign")
    if align is not None and align not in TEXT_ALIGN:
        raise _fail(path, "invalid textAlign")
    if kind == "heading" and attrs.get("level") not in HEADING_LEVELS:
        raise _fail(path, f"heading level must be one of {sorted(HEADING_LEVELS)}")
    if kind == "orderedList" and attrs.get("start") is not None:
        start = attrs["start"]
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not 0 <= start <= MAX_LIST_START
        ):
            raise _fail(path, "invalid list start")
    if kind == "codeBlock" and attrs.get("language") is not None:
        language = attrs["language"]
        if not isinstance(language, str) or not set(language) <= CODE_LANGUAGE_CHARS:
            raise _fail(path, "invalid code language")
    if kind == "image" and not isinstance(attrs.get("src"), str):
        raise _fail(path, "image needs a src")
    for span in ("colspan", "rowspan"):
        value = attrs.get(span)
        if value is not None and (not isinstance(value, int) or not 1 <= value <= MAX_SPAN):
            raise _fail(path, f"invalid {span}")


def _check_marks(node: Node, path: str) -> None:
    marks = node.get("marks", [])
    if not isinstance(marks, list):
        raise _fail(path, "marks must be a list")
    for index, mark in enumerate(marks):
        mark_path = f"{path}.marks[{index}]"
        if not isinstance(mark, Mapping) or mark.get("type") not in _MARKS:
            raise _fail(mark_path, "unknown mark")
        attrs = _attrs(mark, _MARKS[mark["type"]], mark_path)
        if mark["type"] == "link" and safe_link(attrs.get("href")) is None:
            raise _fail(mark_path, "links must be http(s) or mailto")


def validate(doc: object) -> dict[str, Any]:
    """Return the document if it is valid, raise InvalidRichTextError otherwise."""
    if not isinstance(doc, Mapping) or doc.get("type") != "doc":
        raise _fail("$", "root must be a doc node")
    budget = {"nodes": 0, "text": 0}

    def walk(node: object, path: str, depth: int, allowed: frozenset[str]) -> None:
        if depth > MAX_DEPTH:
            raise _fail(path, "document is nested too deeply")
        if not isinstance(node, Mapping):
            raise _fail(path, "node must be an object")
        kind = node.get("type")
        if kind not in _NODES or kind not in allowed:
            raise _fail(path, f"node {kind!r} is not allowed here")
        budget["nodes"] += 1
        if budget["nodes"] > MAX_NODES:
            raise _fail(path, "document has too many nodes")
        children, attr_names = _NODES[kind]
        _check_attrs(kind, _attrs(node, attr_names, path), path)
        if kind == "text":
            text = node.get("text")
            if not isinstance(text, str) or not text:
                raise _fail(path, "text node needs non-empty text")
            budget["text"] += len(text)
            if budget["text"] > MAX_TEXT:
                raise _fail(path, "document text is too long")
            _check_marks(node, path)
            return
        content = node.get("content", [])
        if not isinstance(content, list):
            raise _fail(path, "content must be a list")
        if children is None:
            if content:
                raise _fail(path, f"{kind} cannot have content")
            return
        for index, child in enumerate(content):
            walk(child, f"{path}.content[{index}]", depth + 1, children)

    walk(doc, "$", 0, frozenset({"doc"}))
    return dict(doc)


# --- rendering ----------------------------------------------------------------


def _class(attrs: Mapping[str, Any]) -> str:
    align = attrs.get("textAlign")
    return f' class="ta-{align}"' if align in TEXT_ALIGN and align != "left" else ""


def _wrap_marks(html: str, marks: list[Mapping[str, Any]]) -> str:
    simple = {
        "bold": "strong",
        "italic": "em",
        "underline": "u",
        "strike": "s",
        "code": "code",
        "highlight": "mark",
        "subscript": "sub",
        "superscript": "sup",
    }
    # The first mark is the outermost element.
    for mark in reversed(marks):
        kind = mark["type"]
        if kind == "link":
            href = safe_link((mark.get("attrs") or {}).get("href")) or "#"
            external = not href.startswith("mailto:")
            extra = ' target="_blank" rel="noopener noreferrer nofollow"' if external else ""
            html = f'<a href="{escape(href)}"{extra}>{html}</a>'
        else:
            tag = simple[kind]
            html = f"<{tag}>{html}</{tag}>"
    return html


def render_html(doc: Mapping[str, Any], options: RenderOptions) -> str:
    """Render a document that already passed `validate`."""

    def children(node: Node) -> str:
        return "".join(render(child) for child in node.get("content", []))

    def cell(tag: str) -> Callable[[Node], str]:
        def _render(node: Node) -> str:
            attrs = node.get("attrs") or {}
            spans = "".join(
                f' {name}="{int(attrs[name])}"'
                for name in ("colspan", "rowspan")
                if attrs.get(name) not in (None, 1)
            )
            return f"<{tag}{spans}>{children(node)}</{tag}>"

        return _render

    def image(node: Node) -> str:
        attrs = node.get("attrs") or {}
        src = str(attrs.get("src", ""))
        if not src.startswith(f"{options.image_base_url}/"):
            return ""  # a foreign image is dropped instead of hot-linked
        alt = escape(str(attrs.get("alt") or ""))
        return f'<img src="{escape(src)}" alt="{alt}" loading="lazy">'

    def ordered(node: Node) -> str:
        start = (node.get("attrs") or {}).get("start")
        start_attr = f' start="{int(start)}"' if isinstance(start, int) and start != 1 else ""
        return f"<ol{start_attr}>{children(node)}</ol>"

    def code_block(node: Node) -> str:
        language = (node.get("attrs") or {}).get("language")
        lang_class = f' class="language-{escape(language)}"' if language else ""
        code = "".join(escape(str(child.get("text", ""))) for child in node.get("content", []))
        return f"<pre><code{lang_class}>{code}</code></pre>"

    renderers: dict[str, Callable[[Node], str]] = {
        "doc": children,
        "paragraph": lambda n: f"<p{_class(n.get('attrs') or {})}>{children(n)}</p>",
        "heading": lambda n: (
            f"<h{n['attrs']['level']}{_class(n['attrs'])}>{children(n)}</h{n['attrs']['level']}>"
        ),
        "bulletList": lambda n: f"<ul>{children(n)}</ul>",
        "orderedList": ordered,
        "listItem": lambda n: f"<li>{children(n)}</li>",
        "blockquote": lambda n: f"<blockquote>{children(n)}</blockquote>",
        "codeBlock": code_block,
        "horizontalRule": lambda _: "<hr>",
        "image": image,
        "table": lambda n: f"<table><tbody>{children(n)}</tbody></table>",
        "tableRow": lambda n: f"<tr>{children(n)}</tr>",
        "tableHeader": cell("th"),
        "tableCell": cell("td"),
        "hardBreak": lambda _: "<br>",
        "text": lambda n: _wrap_marks(escape(str(n["text"])), list(n.get("marks", []))),
    }

    def render(node: Node) -> str:
        return renderers[str(node["type"])](node)

    return render(doc)


def plain_text(doc: Mapping[str, Any]) -> str:
    """Text content with block boundaries as newlines (search, previews, emptiness checks)."""
    parts: list[str] = []

    def walk(node: Node) -> None:
        kind = node.get("type")
        if kind == "text":
            parts.append(str(node.get("text", "")))
        elif kind == "hardBreak":
            parts.append("\n")
        for child in node.get("content", []):
            walk(child)
        if kind in _BLOCK_CHILDREN or kind == "listItem":
            parts.append("\n")

    walk(doc)
    return "\n".join(line.strip() for line in "".join(parts).splitlines() if line.strip())


@dataclass(frozen=True, slots=True)
class Section:
    heading: str
    text: str


def sections(doc: Mapping[str, Any]) -> list[Section]:
    """Split a document at its headings: the natural boundaries for search chunks.

    Text before the first heading becomes a section with an empty heading. Sections
    without text are dropped.
    """
    found: list[Section] = []
    heading, blocks = "", list[str]()
    for node in doc.get("content", []):
        if node.get("type") == "heading":
            if blocks:
                found.append(Section(heading, "\n".join(blocks)))
            heading, blocks = plain_text(node), []
            continue
        text = plain_text({"type": "doc", "content": [node]})
        if text:
            blocks.append(text)
    if blocks:
        found.append(Section(heading, "\n".join(blocks)))
    return found
