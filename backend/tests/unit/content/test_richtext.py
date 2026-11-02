from typing import Any

import pytest

from portfolio.contexts.content.domain import richtext
from portfolio.contexts.content.domain.errors import InvalidRichTextError
from portfolio.contexts.content.domain.richtext import RenderOptions

OPTIONS = RenderOptions(image_base_url="https://files.test")


def doc(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "content": list(blocks)}


def p(*inline: dict[str, Any], **attrs: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "paragraph", "content": list(inline)}
    if attrs:
        node["attrs"] = attrs
    return node


def t(text: str, *marks: dict[str, Any]) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    return node


def render(document: dict[str, Any]) -> str:
    return richtext.render_html(richtext.validate(document), OPTIONS)


class TestRendering:
    def test_escapes_text(self) -> None:
        assert render(doc(p(t("<script>alert(1)</script> & co")))) == (
            "<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; co</p>"
        )

    def test_marks_nest_in_order(self) -> None:
        html = render(doc(p(t("x", {"type": "bold"}, {"type": "italic"}))))
        assert html == "<p><strong><em>x</em></strong></p>"

    @pytest.mark.parametrize(
        ("mark", "tag"),
        [
            ("underline", "u"),
            ("strike", "s"),
            ("code", "code"),
            ("highlight", "mark"),
            ("subscript", "sub"),
            ("superscript", "sup"),
        ],
    )
    def test_simple_marks(self, mark: str, tag: str) -> None:
        assert render(doc(p(t("x", {"type": mark})))) == f"<p><{tag}>x</{tag}></p>"

    def test_external_links_open_safely(self) -> None:
        link = {"type": "link", "attrs": {"href": "https://a.dev/?q=1&r=2", "target": "_blank"}}
        assert render(doc(p(t("a", link)))) == (
            '<p><a href="https://a.dev/?q=1&amp;r=2" target="_blank" '
            'rel="noopener noreferrer nofollow">a</a></p>'
        )

    def test_mailto_links_stay_in_place(self) -> None:
        link = {"type": "link", "attrs": {"href": "mailto:e@x.dev"}}
        assert render(doc(p(t("mail", link)))) == '<p><a href="mailto:e@x.dev">mail</a></p>'

    def test_headings_alignment_and_breaks(self) -> None:
        html = render(
            doc(
                {
                    "type": "heading",
                    "attrs": {"level": 2, "textAlign": "center"},
                    "content": [t("H")],
                },
                p(t("a"), {"type": "hardBreak"}, t("b"), textAlign="left"),
                p(textAlign="right"),
            )
        )
        assert html == '<h2 class="ta-center">H</h2><p>a<br>b</p><p class="ta-right"></p>'

    def test_lists_quote_rule(self) -> None:
        item = {"type": "listItem", "content": [p(t("i"))]}
        html = render(
            doc(
                {"type": "bulletList", "content": [item]},
                {"type": "orderedList", "attrs": {"start": 3}, "content": [item]},
                {"type": "orderedList", "attrs": {"start": 1}, "content": [item]},
                {"type": "blockquote", "content": [p(t("q"))]},
                {"type": "horizontalRule"},
            )
        )
        assert html == (
            '<ul><li><p>i</p></li></ul><ol start="3"><li><p>i</p></li></ol>'
            "<ol><li><p>i</p></li></ol><blockquote><p>q</p></blockquote><hr>"
        )

    def test_code_block_is_escaped_and_tagged(self) -> None:
        html = render(
            doc({"type": "codeBlock", "attrs": {"language": "python"}, "content": [t("a < b")]})
        )
        assert html == '<pre><code class="language-python">a &lt; b</code></pre>'
        plain = render(doc({"type": "codeBlock", "content": [t("x")]}))
        assert plain == "<pre><code>x</code></pre>"

    def test_tables_with_spans(self) -> None:
        cell = {"type": "tableCell", "attrs": {"colspan": 2, "rowspan": 1}, "content": [p(t("c"))]}
        head = {"type": "tableHeader", "content": [p(t("h"))]}
        html = render(
            doc({"type": "table", "content": [{"type": "tableRow", "content": [head, cell]}]})
        )
        assert html == (
            '<table><tbody><tr><th><p>h</p></th><td colspan="2"><p>c</p></td></tr></tbody></table>'
        )

    def test_images_only_from_our_storage(self) -> None:
        ours = {"type": "image", "attrs": {"src": "https://files.test/a.png", "alt": 'a "b"'}}
        foreign = {"type": "image", "attrs": {"src": "https://evil.test/track.png"}}
        assert render(doc(ours, foreign)) == (
            '<img src="https://files.test/a.png" alt="a &quot;b&quot;" loading="lazy">'
        )

    def test_null_attributes_from_tiptap_are_fine(self) -> None:
        node = p(t("x"), textAlign=None)
        assert render(doc(node)) == "<p>x</p>"


class TestValidation:
    @pytest.mark.parametrize(
        ("document", "reason"),
        [
            ("nope", "root must be a doc"),
            ({"type": "paragraph"}, "root must be a doc"),
            (doc({"type": "script"}), "not allowed"),
            (doc(t("bare text")), "not allowed"),
            (doc(p(p())), "not allowed"),
            (doc("x"), "node must be an object"),  # type: ignore[arg-type]
            (doc(p(t(""))), "non-empty text"),
            (doc(p(t("x", {"type": "font"}))), "unknown mark"),
            (doc(p(t("x", {"type": "link", "attrs": {"href": "javascript:alert(1)"}}))), "links"),
            (doc(p(t("x", {"type": "link", "attrs": {"href": "h" * 3000}}))), "links"),
            (doc(p(t("x", {"type": "bold", "attrs": {"style": "x"}}))), "unknown attributes"),
            ({"type": "doc", "content": {}}, "content must be a list"),
            (doc({"type": "paragraph", "attrs": []}), "attrs must be an object"),
            (doc(p({"type": "text", "text": "x", "marks": "bold"})), "marks must be a list"),
            (doc(p(textAlign="middle")), "textAlign"),
            (doc({"type": "heading", "attrs": {"level": 1}}), "heading level"),
            (doc({"type": "orderedList", "attrs": {"start": -1}}), "list start"),
            (doc({"type": "orderedList", "attrs": {"start": True}}), "list start"),
            (doc({"type": "codeBlock", "attrs": {"language": "<x>"}}), "code language"),
            (doc({"type": "image", "attrs": {}}), "image needs a src"),
            (doc({"type": "horizontalRule", "content": [p()]}), "cannot have content"),
            (doc({"type": "tableCell", "attrs": {"colspan": 0}}), "not allowed"),
        ],
    )
    def test_rejects(self, document: object, reason: str) -> None:
        with pytest.raises(InvalidRichTextError, match=reason):
            richtext.validate(document)

    def test_rejects_bad_spans(self) -> None:
        cell = {"type": "tableCell", "attrs": {"rowspan": 99}}
        row = {"type": "tableRow", "content": [cell]}
        with pytest.raises(InvalidRichTextError, match="rowspan"):
            richtext.validate(doc({"type": "table", "content": [row]}))

    def test_rejects_documents_too_deep(self) -> None:
        node: dict[str, Any] = p(t("x"))
        for _ in range(richtext.MAX_DEPTH):
            node = {"type": "blockquote", "content": [node]}
        with pytest.raises(InvalidRichTextError, match="too deeply"):
            richtext.validate(doc(node))

    def test_rejects_too_many_nodes(self) -> None:
        with pytest.raises(InvalidRichTextError, match="too many nodes"):
            richtext.validate(doc(*[{"type": "horizontalRule"}] * (richtext.MAX_NODES + 1)))

    def test_rejects_too_much_text(self) -> None:
        big = t("x" * (richtext.MAX_TEXT // 2 + 1))
        with pytest.raises(InvalidRichTextError, match="too long"):
            richtext.validate(doc(p(big), p(big)))


def test_plain_text_keeps_block_boundaries() -> None:
    document = doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [t("Title")]},
        p(t("one"), {"type": "hardBreak"}, t("two")),
        {"type": "bulletList", "content": [{"type": "listItem", "content": [p(t("item"))]}]},
        p(),
    )
    assert richtext.plain_text(document) == "Title\none\ntwo\nitem"


def test_safe_link() -> None:
    assert richtext.safe_link(" https://a.dev ") == "https://a.dev"
    assert richtext.safe_link(42) is None
    assert richtext.safe_link("ftp://a.dev") is None
