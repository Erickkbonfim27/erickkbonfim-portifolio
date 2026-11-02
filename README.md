# Erick Kopak Bonfim — Portfolio

The backend behind my portfolio: a public REST API, a remote MCP server you can
plug into Claude, ChatGPT or Codex to ask about my work, a chat agent with
grounding and evals, and an admin area where I write the content.

The repository holds the code and the architecture, not the data. Content lives
only in the production database.

> Work in progress. Phases 1 to 4 are in place: admin, content, files, contacts,
> worker, public API, site, hybrid search and the MCP server.
> See [`docs/decisions.md`](docs/decisions.md) for the decisions and the delivery order.

## Use it from your AI assistant

The portfolio is an MCP server: `https://api.<domain>/mcp` (Streamable HTTP, no
authentication). Add it as a custom connector in Claude or ChatGPT, or:

```bash
claude mcp add --transport http erick-portfolio https://api.<domain>/mcp
```

Then ask things like "has Erick run RAG in production?". Tools and prompts are
listed in [`docs/public-api.md`](docs/public-api.md#mcp).

## Architecture

Hexagonal, one bounded context per concern. Each context has `domain/` (pure,
no framework), `application/` (use cases and the ports they need),
`infrastructure/` (adapters: SQLAlchemy, Argon2…) and `interfaces/` (HTTP, MCP,
CLI). `import-linter` fails the build when a boundary is crossed.

```
backend/src/portfolio/
├── bootstrap.py          composition root: the only place that knows the adapters
├── main.py               FastAPI app factory
├── mcp_server.py         the MCP server: tools and prompts over the same use cases
├── bridges.py            adapters that let one context use another without importing it
├── worker.py             outbox relay, RabbitMQ consumers, daily jobs
├── cli.py                `portfolio create-admin | worker | setup-storage`
├── kernel/               value objects shared by contexts (Email)
├── platform/             settings, database, outbox, RabbitMQ, rate limits, jobs
└── contexts/
    ├── identity/         admin auth: Argon2, server-side sessions, progressive lockout
    ├── content/          bilingual entries, TipTap rich text, draft/published, events
    ├── files/            uploads to S3-compatible storage, type checked by magic bytes
    ├── contacts/         public contact endpoint, admin inbox, emails, 12-month retention
    ├── search/           chunking, Qdrant hybrid index (dense + BM25), RRF, BM25 fallback
    └── ops/              health checks
```

The site (`frontend/`) is React, Vite and TypeScript, ported from the Claude
Design handoff. It reads the public API ([`docs/public-api.md`](docs/public-api.md))
and falls back to the design copy when the API has nothing yet.

## Running locally

Requirements: [uv](https://docs.astral.sh/uv/). There is no Docker here: the app
runs locally and reaches PostgreSQL (and later Qdrant, RabbitMQ, MinIO,
Langfuse) through the variables in `.env`.

```bash
cp .env.example .env      # fill in DATABASE_URL and the rest
make install
make migrate
make create-admin
make dev-api              # http://localhost:8000/docs
```

`make help` lists every command. `make check` runs lint, `mypy --strict`, the
architecture contracts and the tests with a 100% coverage gate.

Integration tests create a temporary database from `TEST_DATABASE_ADMIN_URL`,
share it across the run (each test rolled back), and drop it at the end.

## Deploy

Easypanel builds each app with Nixpacks, one service per app on the same VPS:

| Service | Build path | Notes |
|---|---|---|
| API | `/backend` | `backend/nixpacks.toml` |
| Worker | `/backend` | same build, `NIXPACKS_START_CMD=.venv/bin/portfolio worker` |
| Site | `/frontend` | `frontend/nixpacks.toml`, served by Caddy. Build env `VITE_API_URL`; runtime env `API_ORIGIN`, `FILES_ORIGIN` |

`CORS_ORIGINS` on the API must include the site's origin.
Migrations are applied by hand with `make migrate`, never on boot.

## License

[MIT](LICENSE)
