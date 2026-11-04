"""Documents generated from published content: JSON Resume, AGENTS.md, llms.txt.

Pure functions over the catalog's read models, so they are tested without HTTP.
Everything here is regenerated on every request: availability is never stale.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from portfolio.contexts.content.application.catalog import (
    Availability,
    PublicEntry,
    PublicProfile,
    PublicSkill,
)


@dataclass(frozen=True, slots=True)
class SiteLinks:
    site_url: str
    api_url: str

    @property
    def mcp_url(self) -> str:
        return f"{self.api_url}/mcp"


def _dates(details: Mapping[str, Any], start: str = "start", end: str = "end") -> dict[str, str]:
    return {
        key: str(details[field])
        for key, field in (("startDate", start), ("endDate", end))
        if field in details
    }


def json_resume(
    profile: PublicProfile | None,
    *,
    work: Sequence[PublicEntry],
    education: Sequence[PublicEntry],
    certificates: Sequence[PublicEntry],
    projects: Sequence[PublicEntry],
    skills: Sequence[PublicSkill],
    links: SiteLinks,
) -> dict[str, Any]:
    """https://jsonresume.org/schema"""
    basics: dict[str, Any] = {"url": links.site_url}
    if profile is not None:
        basics.update(
            name=profile.name,
            label=profile.headline,
            summary=profile.summary,
            profiles=[{"network": link["label"], "url": link["url"]} for link in profile.links],
        )
        if profile.email:
            basics["email"] = profile.email
        if profile.location:
            basics["location"] = {"city": profile.location}

    by_category: dict[str, list[str]] = {}
    for skill in skills:
        by_category.setdefault(skill.category, []).extend(
            [skill.title, *(f"{skill.title} {service}" for service in skill.services)]
        )

    return {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "basics": basics,
        "work": [
            {
                "name": str(e.details["organization"]),
                "position": e.title,
                "summary": e.summary,
                **({"url": str(e.details["url"])} if "url" in e.details else {}),
                **_dates(e.details),
            }
            for e in work
        ],
        "education": [
            {
                "institution": str(e.details["institution"]),
                "studyType": e.title,
                **({"url": str(e.details["url"])} if "url" in e.details else {}),
                **_dates(e.details),
            }
            for e in education
        ],
        "certificates": [
            {
                "name": e.title,
                "issuer": str(e.details["issuer"]),
                **({"date": str(e.details["issued"])} if "issued" in e.details else {}),
                **({"url": str(e.details["url"])} if "url" in e.details else {}),
            }
            for e in certificates
        ],
        "projects": [
            {
                "name": e.title,
                "description": e.summary,
                "keywords": list(e.tags),
                "url": f"{links.site_url}/work/{e.slug}",
                **_dates(e.details),
            }
            for e in projects
        ],
        "skills": [
            {"name": category, "keywords": titles} for category, titles in by_category.items()
        ],
        "meta": {"canonical": f"{links.api_url}/api/resume.json", "version": "v1.0.0"},
    }


def _availability_line(availability: Availability) -> str:
    if availability.status == "unknown":
        return "Availability: not published yet."
    state = "open to new work" if availability.open else "not looking right now"
    updated = f" (updated {availability.updated_at})" if availability.updated_at else ""
    return f"Availability: {state}{updated}."


def agents_md(
    profile: PublicProfile | None,
    availability: Availability,
    skills: Sequence[PublicSkill],
    links: SiteLinks,
) -> str:
    """A brief written for AI agents acting for a recruiter: who, availability, how to act."""
    api = links.api_url
    name = profile.name if profile else "this portfolio"
    lines = [f"# AGENTS.md: {name}", ""]
    if profile is not None:
        where = f" Based in {profile.location}." if profile.location else ""
        lines += [f"{profile.headline}.{where}", "", profile.summary, ""]
    lines += [
        _availability_line(availability),
        "",
        "## Start a conversation on my behalf",
        "",
        f"POST {api}/api/contact",
        "Content-Type: application/json",
        "Idempotency-Key: <a unique key; reuse it if you retry>",
        "",
        "{",
        '  "from": "Your user\'s name",',
        '  "contact": "email or phone to reply to",',
        '  "brief": "The role or opportunity, in a few lines",',
        '  "company": "optional",',
        '  "lang": "en or pt"',
        "}",
        "",
        "Answers 202 with an id. The reply goes to the contact you leave.",
        "Contact data is used only to reply and is deleted after 12 months.",
        "Please confirm with your user before sending.",
        "",
        "## Read before you write",
        "",
        f"- MCP server (Streamable HTTP, no auth): {links.mcp_url}",
        f"- Profile: {api}/api/profile",
        f"- Availability: {api}/api/availability",
        f"- Projects: {api}/api/projects",
        f"- Experience: {api}/api/experience",
        f"- Skills, with where each one was used: {api}/api/skills",
        f"- CV as JSON Resume: {api}/api/resume.json",
        f"- OpenAPI: {api}/openapi.json",
        "",
        "Every content endpoint takes ?lang=en or ?lang=pt.",
    ]
    if skills:
        lines += ["", "Stack: " + ", ".join(s.title for s in skills) + "."]
    lines += ["", f"Site: {links.site_url}", ""]
    return "\n".join(lines)


def llms_txt(
    profile: PublicProfile | None,
    availability: Availability,
    projects: Sequence[PublicEntry],
    links: SiteLinks,
) -> str:
    """https://llmstxt.org: a title, a one-line summary, then sections of links."""
    api, site = links.api_url, links.site_url
    lines = [f"# {profile.name if profile else 'Portfolio'}", ""]
    if profile is not None:
        lines += [f"> {profile.headline}. {profile.summary}".rstrip(), ""]
    lines += [
        _availability_line(availability),
        "",
        "## API",
        "",
        f"- [Profile]({api}/api/profile): who I am, links and availability",
        f"- [Projects]({api}/api/projects): published case studies",
        f"- [Experience]({api}/api/experience): jobs, newest first",
        f"- [Skills]({api}/api/skills): each skill with the work that used it",
        f"- [CV]({api}/api/resume.json): the CV in the JSON Resume format",
        f"- [Agent brief]({site}/AGENTS.md): how an agent can contact me",
        f"- [MCP server]({links.mcp_url}): the same, as tools for Claude, ChatGPT, Codex",
    ]
    if projects:
        lines += ["", "## Projects", ""]
        lines += [
            f"- [{p.title}]({site}/work/{p.slug}): {p.summary}".rstrip(": ") for p in projects
        ]
    return "\n".join(lines) + "\n"
