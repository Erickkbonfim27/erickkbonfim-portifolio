"""Kind-specific structured fields (dates, organization, links…).

Stored as JSON next to the entry, but validated here against a small schema per
kind: unknown keys are rejected, so nothing unexpected reaches the public API.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from portfolio.contexts.content.domain.errors import InvalidEntryError
from portfolio.contexts.content.domain.kinds import Kind
from portfolio.kernel.email import Email, InvalidEmailError

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_LINKS = 10
MAX_URL = 2000

# Set by the domain, never accepted from input.
SERVER_MANAGED = frozenset({"availability_updated_at"})

FieldType = Literal["text", "month", "url", "email", "choice", "links"]


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    type: FieldType
    required: bool = False
    choices: tuple[str, ...] = ()
    max_length: int = 160


_PERIOD = (Field("start", "month"), Field("end", "month"))

SCHEMAS: dict[Kind, tuple[Field, ...]] = {
    Kind.PROFILE: (
        Field("name", "text", required=True),
        Field("location", "text"),
        Field("email", "email"),
        Field("links", "links"),
        Field("availability", "choice", required=True, choices=("open", "not_looking")),
    ),
    Kind.EXPERIENCE: (
        Field("organization", "text", required=True),
        Field("location", "text"),
        Field("start", "month", required=True),
        Field("end", "month"),
        Field("url", "url"),
        Field(
            "employment",
            "choice",
            choices=("full_time", "part_time", "contract", "founder", "internship"),
        ),
    ),
    Kind.PROJECT: (
        Field("collection", "choice", required=True, choices=("portfolio", "lab")),
        Field("organization", "text"),
        *_PERIOD,
        Field("state", "choice", choices=("active", "standby", "shipped", "archived")),
        Field("links", "links"),
    ),
    Kind.EDUCATION: (
        Field("institution", "text", required=True),
        *_PERIOD,
        Field("url", "url"),
    ),
    Kind.CERTIFICATE: (
        Field("issuer", "text", required=True),
        Field("issued", "month"),
        Field("url", "url"),
    ),
    Kind.STUDY: (
        Field("medium", "choice", required=True, choices=("book", "course", "paper", "topic")),
        Field("author", "text"),
        Field("url", "url"),
        Field("progress", "choice", choices=("planned", "in_progress", "done")),
    ),
    Kind.WRITING: (Field("published", "month"), Field("url", "url")),
    Kind.POST: (),
    Kind.SKILL: (
        Field(
            "category",
            "choice",
            required=True,
            choices=("language", "framework", "ai", "data", "cloud", "practice", "tool"),
        ),
    ),
}


def _url(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_URL:
        raise InvalidEntryError(f"{name} must be a URL")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidEntryError(f"{name} must be an http(s) URL")
    return value


def _text(value: object, name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise InvalidEntryError(f"{name} must be text up to {max_length} characters")
    return value.strip()


def _value(field: Field, value: object) -> Any:
    match field.type:
        case "text":
            return _text(value, field.name, field.max_length)
        case "month":
            if not isinstance(value, str) or not _MONTH.match(value):
                raise InvalidEntryError(f"{field.name} must be YYYY-MM")
            return value
        case "url":
            return _url(value, field.name)
        case "email":
            try:
                return Email.parse(str(value)).value
            except InvalidEmailError:
                raise InvalidEntryError(f"{field.name} must be an email") from None
        case "choice":
            if value not in field.choices:
                raise InvalidEntryError(f"{field.name} must be one of {list(field.choices)}")
            return value
        case _:  # "links"
            if not isinstance(value, list) or len(value) > MAX_LINKS:
                raise InvalidEntryError(f"{field.name} must be a list of up to {MAX_LINKS}")
            links = []
            for link in value:
                if not isinstance(link, Mapping) or set(link) != {"label", "url"}:
                    raise InvalidEntryError(f"each of {field.name} needs exactly label and url")
                links.append(
                    {"label": _text(link["label"], "label", 60), "url": _url(link["url"], "url")}
                )
            return links


def parse_details(kind: Kind, raw: Mapping[str, Any]) -> dict[str, Any]:
    schema = {field.name: field for field in SCHEMAS[kind]}
    given = {key: value for key, value in raw.items() if key not in SERVER_MANAGED}
    unknown = set(given) - set(schema)
    if unknown:
        raise InvalidEntryError(f"unknown fields for {kind}: {sorted(unknown)}")
    parsed: dict[str, Any] = {}
    for name, field in schema.items():
        value = given.get(name)
        if value is None or value in ("", []):
            if field.required:
                raise InvalidEntryError(f"{name} is required for {kind}")
            continue
        parsed[name] = _value(field, value)
    if "start" in parsed and "end" in parsed and parsed["end"] < parsed["start"]:
        raise InvalidEntryError("end must not be before start")
    return parsed
