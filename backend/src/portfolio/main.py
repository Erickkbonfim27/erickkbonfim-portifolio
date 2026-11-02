from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from portfolio.bootstrap import Container, build_container
from portfolio.contexts.contacts.domain.model import ContactsError
from portfolio.contexts.contacts.interfaces import http as contacts_http
from portfolio.contexts.content.domain.errors import ContentError
from portfolio.contexts.content.interfaces import http as content_http
from portfolio.contexts.content.interfaces import public_http as catalog_http
from portfolio.contexts.content.interfaces.documents import SiteLinks
from portfolio.contexts.files.domain.model import FilesError
from portfolio.contexts.files.interfaces import http as files_http
from portfolio.contexts.identity.interfaces import http as identity_http
from portfolio.contexts.ops.interfaces import http as ops_http
from portfolio.contexts.search.domain.model import SearchError
from portfolio.contexts.search.interfaces import http as search_http
from portfolio.mcp_server import build_mcp_server, mcp_app
from portfolio.platform.settings import Settings
from portfolio.platform.throttle import ThrottleMiddleware, TokenBuckets

# Every admin router is mounted with this dependency, here and only here, so a
# context's router cannot forget authentication (tests check every /admin route).
ADMIN_ONLY = [Depends(identity_http.current_admin)]

REQUESTS_PER_SECOND = 10
BURST = 20
PUBLIC_CACHE = "public, max-age=60, stale-while-revalidate=600"


def _cache_policy(method: str, path: str, code: int) -> str | None:
    """Public reads may be cached briefly; anything under /admin never is."""
    if path.startswith("/admin"):
        return "no-store"
    if path.startswith("/api/search"):
        return None  # queries are too varied to be worth caching
    readable = path.startswith("/api/") or path in ("/AGENTS.md", "/llms.txt")
    if method == "GET" and code == status.HTTP_200_OK and readable:
        return PUBLIC_CACHE
    return None


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """App factory. Run with `uvicorn portfolio.main:create_app --factory`.

    Tests pass their own container (fakes) and never touch the network.
    """
    settings = settings or Settings()
    container = container or build_container(settings)
    links = SiteLinks(settings.public_site_url, settings.public_api_url)
    mcp = build_mcp_server(container, links)
    mcp_routes = mcp_app(mcp).routes  # builds the session manager used below

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield
        await container.close()

    app = FastAPI(
        title="Erick Kopak Bonfim — Portfolio API",
        version="0.3.0",
        description="Erick Kopak Bonfim's portfolio. Read-only content API plus a contact "
        "endpoint. Built for people and for AI agents; see /AGENTS.md.",
        lifespan=lifespan,
        # Interactive docs only outside production; the schema stays public.
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
    )
    app.state.identity = container.identity
    app.state.content = container.content
    app.state.catalog = container.catalog
    app.state.links = links
    app.state.search = container.search
    app.state.files = container.files
    app.state.contacts = container.contacts
    app.state.auth_cookie = container.auth_cookie

    @app.middleware("http")
    async def cache_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        policy = _cache_policy(request.method, request.url.path, response.status_code)
        if policy is not None:
            response.headers.setdefault("Cache-Control", policy)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    # Outermost: throttled requests are refused before any other work.
    app.add_middleware(ThrottleMiddleware, buckets=TokenBuckets(REQUESTS_PER_SECOND, BURST))
    app.add_exception_handler(ContentError, content_http.error_response)
    app.add_exception_handler(FilesError, files_http.error_response)
    app.add_exception_handler(ContactsError, contacts_http.error_response)
    app.add_exception_handler(SearchError, search_http.error_response)

    app.include_router(ops_http.router)
    app.include_router(identity_http.router)
    app.include_router(catalog_http.router)
    app.include_router(catalog_http.documents_router)
    app.include_router(search_http.router)
    app.include_router(contacts_http.public_router)
    app.include_router(content_http.router, dependencies=ADMIN_ONLY)
    app.include_router(files_http.router, dependencies=ADMIN_ONLY)
    app.include_router(contacts_http.admin_router, dependencies=ADMIN_ONLY)
    # The MCP endpoint (/mcp) shares the app, so throttling and CORS apply to it too.
    app.router.routes.extend(mcp_routes)
    return app
