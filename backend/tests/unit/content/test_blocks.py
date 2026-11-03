from pathlib import Path
from typing import Any

import pytest

from portfolio.contexts.content.domain import blocks, richtext
from portfolio.contexts.content.domain.errors import InvalidRichTextError
from portfolio.contexts.content.domain.kinds import Kind
from portfolio.contexts.content.interfaces.seed import (
    SeedEntry,
    SeedError,
    markdown_to_doc,
    upload_files,
)

OWN = "https://files.test"
RENDER = richtext.RenderOptions(image_base_url=OWN)

SAMPLES: dict[str, dict[str, Any]] = {
    "facts": {"items": [{"label": "Problem", "text": "Spreadsheets."}]},
    "metrics": {"items": [{"value": "150", "label": "data sources", "note": "23 areas"}]},
    "note": {"text": "Why I left: we decided to go different ways."},
    "gallery": {
        "layout": "feature",
        "items": [
            {"src": f"{OWN}/a.webp", "alt": "Booth", "caption": "Fairtech", "wide": True},
            {"src": "https://evil.test/b.webp", "alt": "Foreign"},
        ],
    },
    "timeline": {
        "style": "roadbook",
        "title": "Ecosystem",
        "items": [
            {
                "when": "2023",
                "title": "Reuni Challenge",
                "text": "7th nationally.",
                "place": "Brusque",
                "tag": "SS1",
                "image": {"src": f"{OWN}/r.webp", "alt": "Team"},
                "link": {"label": "News", "url": "https://unifebe.edu.br/x"},
            },
            {"when": "2024", "title": "Fair", "image": {"src": "https://evil.test/x", "alt": "x"}},
        ],
    },
    "diagram": {
        "title": "Vizzion on GCP",
        "width": 1200,
        "height": 700,
        "groups": [{"id": "vpc", "label": "VPC", "x": 10, "y": 10, "w": 900, "h": 600}],
        "nodes": [
            {"id": "lb", "label": "Cloud Load Balancing", "x": 20, "y": 20},
            {"id": "main", "label": "vizzion_main", "sub": "Cloud Run", "x": 300, "y": 20},
        ],
        "edges": [{"from": "lb", "to": "main", "label": "HTTPS", "flow": True, "dashed": False}],
        "steps": [{"title": "Entry", "text": "Requests come in.", "focus": ["lb", "vpc"]}],
    },
    "logos": {
        "title": "Integrations",
        "groups": [
            {
                "title": "Government",
                "items": [
                    {"name": "IBGE", "logo": f"{OWN}/ibge.webp", "url": "https://ibge.gov.br"},
                    {"name": "Foreign", "logo": "https://evil.test/l.png", "note": "REST"},
                ],
            }
        ],
    },
    "cases": {
        "items": [
            {
                "title": "RAIS and CAGED",
                "tag": "files",
                "parts": [{"label": "Problem", "text": "One format per file."}],
            }
        ]
    },
    "quote": {
        "text": "They came to ask.",
        "author": "Ana Prado",
        "role": "Vangarden",
        "url": "https://linkedin.com/pulse/x",
    },
    "map": {
        "src": f"{OWN}/streets.geojson",
        "attribution": "© OpenStreetMap contributors",
        "metrics": [
            {
                "key": "nain",
                "label": "Integration",
                "note": "How easy each street is to reach from all the others.",
                "low": "segregated",
                "high": "integrated",
            }
        ],
        "caption": "Downtown Brusque.",
        "legend": {"low": "segregated", "high": "integrated"},
    },
}


def block(kind: str, data: Any, **attrs: Any) -> dict[str, Any]:
    return {"type": "block", "attrs": {"kind": kind, "data": data, **attrs}}


def doc(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "content": list(content)}


def paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


class TestValidation:
    @pytest.mark.parametrize("kind", sorted(SAMPLES))
    def test_every_kind_has_a_valid_sample(self, kind: str) -> None:
        richtext.validate(doc(block(kind, SAMPLES[kind], hidden=False)))

    @pytest.mark.parametrize(
        ("node", "reason"),
        [
            (block("poll", {}), "block kind must be one of"),
            (block("facts", SAMPLES["facts"], hidden="yes"), "hidden: must be true or false"),
            (block("facts", None), "data: must be an object"),
            (block("facts", {"items": []}), "must be a list of 1 to 4"),
            (block("facts", {"items": [{"label": "x"}]}), "text is required"),
            (block("facts", {"items": [{"label": "x", "text": "y", "z": 1}]}), "unknown fields"),
            (block("facts", {"items": [{"label": " ", "text": "y"}]}), "must be text up to 40"),
            (block("quote", {**SAMPLES["quote"], "url": "javascript:x"}), r"http\(s\) URL"),
            (block("quote", {**SAMPLES["quote"], "url": 7}), "must be a URL"),
            (block("gallery", {**SAMPLES["gallery"], "layout": "masonry"}), "must be one of"),
            (
                block("gallery", {"items": [{"src": "s", "alt": "a", "wide": 1}]}),
                "true or false",
            ),
            (block("diagram", {**SAMPLES["diagram"], "width": 9999}), "from 100 to 4000"),
            (block("diagram", {**SAMPLES["diagram"], "width": True}), "from 100 to 4000"),
            (
                block("map", {**SAMPLES["map"], "metrics": [{"key": "NAIN", "label": "x"}]}),
                "a lowercase key",
            ),
        ],
    )
    def test_rejects(self, node: dict[str, Any], reason: str) -> None:
        with pytest.raises(InvalidRichTextError, match=reason):
            richtext.validate(doc(node))

    def test_only_at_the_top_level(self) -> None:
        nested = {
            "type": "blockquote",
            "content": [block("facts", SAMPLES["facts"])],
        }
        with pytest.raises(InvalidRichTextError, match="not allowed here"):
            richtext.validate(doc(nested))

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"groups": [{"id": "lb", "label": "x", "x": 0, "y": 0, "w": 1, "h": 1}]}, "unique"),
            ({"edges": [{"from": "lb", "to": "ghost"}]}, "join existing nodes"),
            ({"steps": [{"title": "x", "text": "y", "focus": ["ghost"]}]}, "nodes or groups"),
        ],
    )
    def test_diagram_references(self, change: dict[str, Any], reason: str) -> None:
        with pytest.raises(InvalidRichTextError, match=reason):
            richtext.validate(doc(block("diagram", {**SAMPLES["diagram"], **change})))

    def test_logo_walls_have_a_total_limit(self) -> None:
        many = [{"name": f"API {n}"} for n in range(blocks.MAX_LOGOS)]
        groups = [{"title": "A", "items": many}, {"title": "B", "items": [{"name": "one more"}]}]
        with pytest.raises(InvalidRichTextError, match="at most 400"):
            richtext.validate(doc(block("logos", {"groups": groups})))


class TestOutput:
    def test_segments_interleave_html_and_blocks(self) -> None:
        body = doc(
            paragraph("Intro"),
            block("metrics", SAMPLES["metrics"]),
            block("facts", SAMPLES["facts"], hidden=True),
            paragraph("Outro"),
        )
        assert richtext.segments(body, RENDER) == [
            {"type": "html", "html": "<p>Intro</p>"},
            {"type": "block", "kind": "metrics", "data": SAMPLES["metrics"]},
            {"type": "html", "html": "<p>Outro</p>"},
        ]

    def test_foreign_images_never_leave_the_server(self) -> None:
        [gallery, timeline, logos, map_] = [
            segment["data"]
            for segment in richtext.segments(
                doc(*(block(k, SAMPLES[k]) for k in ("gallery", "timeline", "logos", "map"))),
                RENDER,
            )
        ]
        assert [item["alt"] for item in gallery["items"]] == ["Booth"]
        assert ["image" in item for item in timeline["items"]] == [True, False]
        assert ["logo" in item for item in logos["groups"][0]["items"]] == [True, False]
        assert map_["src"] == f"{OWN}/streets.geojson"

    def test_blocks_left_empty_are_dropped(self) -> None:
        foreign = {"items": [{"src": "https://evil.test/a.webp", "alt": "x"}]}
        foreign_map = {**SAMPLES["map"], "src": "https://evil.test/s.geojson"}
        foreign_image = {"type": "image", "attrs": {"src": "https://evil.test/i.png"}}
        body = doc(foreign_image, block("gallery", foreign), block("map", foreign_map))
        assert richtext.segments(body, RENDER) == []
        assert richtext.render_html(body, RENDER) == ""

    def test_html_fallback(self) -> None:
        html = richtext.render_html(
            doc(*(block(k, SAMPLES[k]) for k in ("gallery", "quote", "metrics"))), RENDER
        )
        assert '<figure><img src="https://files.test/a.webp" alt="Booth" loading="lazy">' in html
        assert "<figcaption>Fairtech</figcaption>" in html
        assert "evil.test" not in html
        assert "<footer>Ana Prado, Vangarden</footer>" in html
        assert '<ul class="block block-metrics"><li>150 data sources (23 areas)</li></ul>' in html
        bare = {"items": [{"value": "54", "label": "pull requests"}]}
        assert blocks.block_text("metrics", bare) == "54 pull requests"
        no_role = {"text": "Hi", "author": "Ana"}
        assert "<footer>Ana</footer>" in richtext.render_html(doc(block("quote", no_role)), RENDER)
        no_caption = {"items": [{"src": f"{OWN}/a.webp", "alt": "<b>"}]}
        assert "figcaption" not in richtext.render_html(doc(block("gallery", no_caption)), RENDER)

    def test_plain_text_reads_visible_blocks_only(self) -> None:
        body = doc(
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Arch"}],
            },
            block("diagram", SAMPLES["diagram"]),
            block("facts", {"items": [{"label": "Secret", "text": "hidden"}]}, hidden=True),
            block("logos", SAMPLES["logos"]),
        )
        text = richtext.plain_text(body)
        assert "vizzion_main: Cloud Run" in text
        assert "Cloud Load Balancing" in text
        assert "Entry: Requests come in." in text
        assert "IBGE" in text
        assert "Foreign · REST" in text
        assert "Secret" not in text
        assert "https://" not in text
        assert richtext.sections(body)[0].heading == "Arch"

    def test_notes_are_for_the_index_only(self) -> None:
        body = doc(block("facts", SAMPLES["facts"]), block("note", SAMPLES["note"]))
        assert richtext.segments(body, RENDER) == [
            {"type": "block", "kind": "facts", "data": SAMPLES["facts"]}
        ]
        assert "different ways" not in richtext.render_html(body, RENDER)
        assert "different ways" not in richtext.plain_text(body)
        assert "different ways" in richtext.plain_text(body, notes=True)
        assert "different ways" in richtext.sections(body)[0].text

    def test_block_text_of_a_bare_diagram(self) -> None:
        bare = {"width": 100, "height": 100, "nodes": [{"id": "a", "label": "A", "x": 0, "y": 0}]}
        assert blocks.block_text("diagram", bare) == "A"
        assert blocks.block_text("map", SAMPLES["map"]).splitlines()[0] == (
            "© OpenStreetMap contributors"
        )


class TestSeed:
    def test_block_fences(self) -> None:
        source = """## Gallery

```block gallery hidden
{"items": [{"src": "file:photos/a.heic", "alt": "Booth"}]}
```

```python
print("code stays code")
```

```block facts
{"items": [{"label": "Role", "text": "CTO"}]}
```
"""
        content = markdown_to_doc(source)["content"]
        assert content[1] == block(
            "gallery", {"items": [{"src": "file:photos/a.heic", "alt": "Booth"}]}, hidden=True
        )
        assert content[2]["type"] == "codeBlock"
        assert content[3] == block("facts", {"items": [{"label": "Role", "text": "CTO"}]})

    @pytest.mark.parametrize(
        ("source", "reason"),
        [
            ("```block\n{}\n```", "block <kind>"),
            ("```block facts secret\n{}\n```", "block <kind>"),
            ("```block facts\n{not json\n```", "invalid JSON"),
        ],
    )
    def test_bad_fences(self, source: str, reason: str) -> None:
        with pytest.raises(SeedError, match=reason):
            markdown_to_doc(source)

    async def test_files_are_uploaded_once_and_replaced_by_their_url(self, tmp_path: Path) -> None:
        (tmp_path / "photos").mkdir()
        (tmp_path / "photos" / "a.heic").write_bytes(b"photo")
        body = '{"src": "file:photos/a.heic"} {"src": "file:./photos/a.heic"}'
        entry = SeedEntry(
            Kind.PROJECT, "vizzion", {"en": {"title": "V", "body": body}, "pt": {"title": "V"}}
        )
        entry = SeedEntry(entry.kind, entry.slug, entry.raw, tmp_path)
        uploaded: list[Path] = []

        async def upload(path: Path) -> str:
            uploaded.append(path)
            return f"{OWN}/{len(uploaded)}.webp"

        [resolved] = await upload_files([entry], upload)
        assert resolved.raw["en"]["body"] == (
            f'{{"src": "{OWN}/1.webp"}} {{"src": "{OWN}/1.webp"}}'
        )
        assert resolved.raw["pt"] == {"title": "V"}
        assert uploaded == [tmp_path / "photos" / "a.heic"]

    async def test_includes_are_read_before_files_are_uploaded(self, tmp_path: Path) -> None:
        (tmp_path / "wall.json").write_text('{"logo": "file:a.png"}', encoding="utf-8")
        (tmp_path / "a.png").write_bytes(b"png")
        body = "```block logos\n@include wall.json\n```"
        entry = SeedEntry(Kind.PROJECT, "x", {"en": {"body": body}}, tmp_path)

        async def upload(path: Path) -> str:
            return f"{OWN}/{path.name}.webp"

        [resolved] = await upload_files([entry], upload)
        assert resolved.raw["en"]["body"] == f'```block logos\n{{"logo": "{OWN}/a.png.webp"}}\n```'
        missing = SeedEntry(Kind.PROJECT, "x", {"en": {"body": "@include nope.json"}}, tmp_path)
        with pytest.raises(SeedError, match=r"no such file to include nope\.json"):
            await upload_files([missing], upload)

    async def test_missing_files_and_storage(self, tmp_path: Path) -> None:
        entry = SeedEntry(Kind.PROJECT, "x", {"en": {"body": '"file:nope.png"'}}, tmp_path)

        async def upload(path: Path) -> str:
            return "never"

        with pytest.raises(SeedError, match=r"no such file nope\.png"):
            await upload_files([entry], upload)
        with pytest.raises(SeedError, match="need storage"):
            await upload_files([entry], None)
