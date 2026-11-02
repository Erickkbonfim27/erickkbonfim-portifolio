"""The MCP server end to end over HTTP, as a client (Claude, ChatGPT, Codex) sees it."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from tests.unit.content.test_public import seed
from tests.unit.support import World, make_world

HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
    "mcp-protocol-version": "2025-06-18",
}


class Mcp:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self._id = 0

    async def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            message["params"] = params
        response = await self._client.post("/mcp", headers=HEADERS, json=message)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result: dict[str, Any] = (
            await self.rpc("tools/call", {"name": tool, "arguments": arguments})
        )["result"]
        return result


@pytest.fixture
async def world() -> World:
    world = make_world()
    await seed(world)
    await world.search().reindex()
    return world


@asynccontextmanager
async def session(world: World) -> AsyncIterator[Mcp]:
    """Opened inside each test: the MCP session manager's task group must be entered
    and exited by the same task, which a pytest fixture does not guarantee."""
    app = world.app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="https://api.erick.test") as client,
    ):
        yield Mcp(client)


async def test_initialize_describes_the_server(world: World) -> None:
    async with session(world) as mcp:
        result = (
            await mcp.rpc(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            )
        )["result"]
        assert result["serverInfo"]["name"] == "erick-portfolio"
        assert "AI Engineer" in result["instructions"]
        assert {"tools", "prompts"} <= set(result["capabilities"])


async def test_tools_and_their_annotations(world: World) -> None:
    async with session(world) as mcp:
        tools = {t["name"]: t for t in (await mcp.rpc("tools/list"))["result"]["tools"]}
        assert set(tools) == {
            "get_profile",
            "check_availability",
            "list_projects",
            "get_project",
            "get_resume",
            "search_portfolio",
            "get_skills",
            "list_studies",
            "contact_erick",
        }
        read_only = {name for name, t in tools.items() if t["annotations"]["readOnlyHint"]}
        assert read_only == set(tools) - {"contact_erick"}
        assert tools["contact_erick"]["annotations"]["openWorldHint"] is True
        assert set(tools["contact_erick"]["inputSchema"]["required"]) == {
            "from_name",
            "contact",
            "brief",
        }


async def test_profile_and_availability(world: World) -> None:
    async with session(world) as mcp:
        profile = (await mcp.call("get_profile", lang="pt"))["structuredContent"]
        assert (profile["name"], profile["headline"]) == ("Erick", "Engenheiro de IA")
        availability = (await mcp.call("check_availability"))["structuredContent"]
        assert availability == {"status": "open", "open": True, "updated_at": "2026-11-02"}


async def test_projects(world: World) -> None:
    async with session(world) as mcp:
        listed = (await mcp.call("list_projects", collection="lab"))["structuredContent"]["result"]
        assert [p["slug"] for p in listed] == ["prospecta"]
        assert listed[0]["url"] == "https://erick.test/work/prospecta"
        project = (await mcp.call("get_project", slug="vizzion"))["structuredContent"]
        assert project["body"] == "<b>bold</b>"  # plain text for the model, not HTML
        assert project["skills"] == ["Python"]
        assert project["attachments"][0]["label"] == "Deck"


async def test_unknown_project_is_a_tool_error(world: World) -> None:
    async with session(world) as mcp:
        result = await mcp.call("get_project", slug="nope")
        assert result["isError"] is True
        assert "nope" in result["content"][0]["text"]


async def test_resume_skills_studies(world: World) -> None:
    async with session(world) as mcp:
        resume = (await mcp.call("get_resume"))["structuredContent"]
        assert resume["basics"]["name"] == "Erick"
        skills = (await mcp.call("get_skills", category="language"))["structuredContent"]["result"]
        assert [s["slug"] for s in skills] == ["python"]
        assert (await mcp.call("get_skills", category="cloud"))["structuredContent"]["result"] == []
        assert (await mcp.call("list_studies"))["structuredContent"]["result"] == []


async def test_search(world: World) -> None:
    async with session(world) as mcp:
        hits = (await mcp.call("search_portfolio", query="Loopia", limit=3))["structuredContent"][
            "result"
        ]
        assert hits[0]["slug"] == "loopia"
        assert hits[0]["url"] is None  # experiences have no page of their own
        invalid = await mcp.call("search_portfolio", query="   ")
        assert invalid["isError"] is True


async def test_contact_goes_through_the_same_rules(world: World) -> None:
    async with session(world) as mcp:
        arguments = {
            "from_name": "Ana",
            "contact": "ana@corp.dev",
            "brief": "AI Engineer role, remote.",
            "idempotency_key": "agent-1",
        }
        first = (await mcp.call("contact_erick", **arguments))["structuredContent"]
        again = (await mcp.call("contact_erick", **arguments))["structuredContent"]
        assert first["id"] == again["id"]
        [stored] = world.contacts.data.values()
        assert stored.form.name == "Ana"
        assert any(key.startswith("mcp:") for _, key in world.limiter.hits)
        bad = await mcp.call("contact_erick", from_name="A", contact="a@b.co", brief="short")
        assert bad["isError"] is True


async def test_prompts(world: World) -> None:
    async with session(world) as mcp:
        prompts = {p["name"] for p in (await mcp.rpc("prompts/list"))["result"]["prompts"]}
        assert prompts == {"hire_erick", "career_story"}
        hire = (
            await mcp.rpc(
                "prompts/get",
                {"name": "hire_erick", "arguments": {"role": "AI Engineer", "company": "Acme"}},
            )
        )["result"]["messages"][0]["content"]["text"]
        assert "AI Engineer at Acme" in hire
        assert "contact_erick" in hire
        generic = (await mcp.rpc("prompts/get", {"name": "hire_erick", "arguments": {}}))["result"]
        assert "for a role" in generic["messages"][0]["content"]["text"]
        story = (
            await mcp.rpc("prompts/get", {"name": "career_story", "arguments": {"lang": "pt"}})
        )["result"]["messages"][0]["content"]["text"]
        assert story.startswith("In Portuguese")


async def test_agent_documents_point_to_the_mcp_server(world: World) -> None:
    app = world.app()
    async with AsyncClient(transport=ASGITransport(app), base_url="https://a.t") as client:
        agents = (await client.get("/AGENTS.md")).text
        llms = (await client.get("/llms.txt")).text
    assert "MCP server (Streamable HTTP, no auth): https://api.erick.test/mcp" in agents
    assert "[MCP server](https://api.erick.test/mcp)" in llms
