from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from portfolio.contexts.contacts.interfaces import http as contacts_http
from portfolio.contexts.content.interfaces import http as content_http
from portfolio.contexts.files.interfaces import http as files_http
from tests.unit.identity.fakes import SESSION_TTL
from tests.unit.support import COOKIE, World, make_world

EMAIL = "erick@example.dev"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def world() -> World:
    return make_world()


@pytest.fixture
async def client(world: World) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(world.app())
    async with AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


async def login(client: AsyncClient, world: World) -> None:
    await world.identity.use_cases.create_admin(EMAIL, PASSWORD)
    response = await client.post("/admin/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 204


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.json() == {"status": "ok"}


async def test_login_sets_a_strict_http_only_cookie(client: AsyncClient, world: World) -> None:
    await world.identity.use_cases.create_admin(EMAIL, PASSWORD)
    response = await client.post("/admin/auth/login", json={"email": EMAIL, "password": PASSWORD})
    header = response.headers["set-cookie"]
    assert header.startswith(f"{COOKIE}=token-1;")
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attribute in header


async def test_wrong_password_is_401(client: AsyncClient, world: World) -> None:
    await world.identity.use_cases.create_admin(EMAIL, PASSWORD)
    response = await client.post(
        "/admin/auth/login", json={"email": EMAIL, "password": "wrong password!!"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


async def test_locked_account_is_429_with_retry_after(client: AsyncClient, world: World) -> None:
    await world.identity.use_cases.create_admin(EMAIL, PASSWORD)
    for _ in range(5):
        await client.post("/admin/auth/login", json={"email": EMAIL, "password": "wrong pass!!"})
    response = await client.post("/admin/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


async def test_oversized_password_is_rejected_before_hashing(client: AsyncClient) -> None:
    response = await client.post("/admin/auth/login", json={"email": EMAIL, "password": "x" * 500})
    assert response.status_code == 422


async def test_me_requires_a_session(client: AsyncClient) -> None:
    assert (await client.get("/admin/auth/me")).status_code == 401
    client.cookies.set(COOKIE, "forged")
    assert (await client.get("/admin/auth/me")).status_code == 401


async def test_me_with_a_session(client: AsyncClient, world: World) -> None:
    await login(client, world)
    response = await client.get("/admin/auth/me")
    assert response.json() == {"email": EMAIL}


async def test_expired_session_is_401(client: AsyncClient, world: World) -> None:
    await login(client, world)
    world.clock.advance(SESSION_TTL + timedelta(seconds=1))
    assert (await client.get("/admin/auth/me")).status_code == 401


async def test_logout_revokes_the_session_and_clears_the_cookie(
    client: AsyncClient, world: World
) -> None:
    await login(client, world)
    response = await client.post("/admin/auth/logout")
    assert response.status_code == 204
    assert f'{COOKIE}=""' in response.headers["set-cookie"]
    assert world.identity.store.sessions == {}


async def test_logout_without_a_session(client: AsyncClient) -> None:
    assert (await client.post("/admin/auth/logout")).status_code == 204


async def test_admin_routes_are_not_in_the_public_schema(client: AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert not any(path.startswith("/admin") for path in paths)
    assert {"/health/live", "/api/contact", "/api/profile", "/AGENTS.md"} <= set(paths)


ADMIN_ROUTERS = (content_http.router, files_http.router, contacts_http.admin_router)


async def test_every_admin_route_requires_a_session(client: AsyncClient) -> None:
    """Guards against an admin router mounted without the session dependency."""
    admin_routes = [
        route for router in ADMIN_ROUTERS for route in router.routes if isinstance(route, APIRoute)
    ]
    assert len(admin_routes) > 10
    sample_id = "00000000-0000-0000-0000-000000000000"
    for route in admin_routes:
        for method in route.methods or set():
            path = route.path.replace("{entry_id}", sample_id)
            path = path.replace("{file_id}", sample_id).replace("{contact_id}", sample_id)
            response = await client.request(method, path)
            assert response.status_code == 401, f"{method} {route.path} is open"


async def test_cors_allows_the_frontend_with_credentials(client: AsyncClient) -> None:
    response = await client.options(
        "/admin/auth/me",
        headers={"Origin": "https://erick.dev", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "https://erick.dev"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_docs_are_off_in_production(world: World) -> None:
    assert world.app(app_env="production").docs_url is None


async def test_shutdown_closes_the_container(world: World) -> None:
    app = world.app()
    async with app.router.lifespan_context(app):
        assert not world.closer.closed
    assert world.closer.closed
