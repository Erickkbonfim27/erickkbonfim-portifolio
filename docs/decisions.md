# Architecture decisions

The decisions behind this repository, written down before the code. Each one
records what was chosen and why. Content decisions (what is published about
each job or project) are not here: content lives only in the production
database, never in the repository.

## Product

- One backend serving four surfaces: a public REST API, a remote MCP server
  (Streamable HTTP), a chat agent for the website, and an authenticated admin
  area for writing content.
- The repository is public (MIT) and contains only code. Data lives only in
  production. `.env.example` lists every variable; `.env` is never committed.
- Content is bilingual (English default, Portuguese). Every query takes a `lang`.

## Backend

- Python 3.13, `uv`, FastAPI, hexagonal architecture. Each bounded context has
  `domain/` (pure, framework-free), `application/` (use cases and ports),
  `infrastructure/` (adapters) and `interfaces/` (HTTP, MCP, CLI). Boundaries
  are enforced by `import-linter`.
- Bounded contexts: `identity` (admin auth), `content` (entities, rich text,
  draft/published, outbox), `contacts` (contact requests and their emails),
  `files` (attachments), `search` (indexing and hybrid retrieval), `assistant`
  (the agent), `ops` (health, status). Contexts are created when their phase
  starts. Contexts never import each other; what more than one needs (the
  `Email` value object) lives in a small shared kernel.
- PostgreSQL is the source of truth. Qdrant is a derived index that can be
  rebuilt from Postgres at any time (`make reindex`).
- Alembic migrations, applied by hand (`make migrate`), never on boot.
- Publishing goes through a transactional outbox: the event is written in the
  same transaction as the entity, a relay publishes it to RabbitMQ, and an
  idempotent consumer (upsert by entity id + version, retry, DLQ) updates Qdrant.
  Writing to Postgres and RabbitMQ directly would be a dual write.
- Scheduled jobs run inside the worker (APScheduler) behind a Postgres advisory
  lock, so they run once even with several workers. Every run is recorded.
- Files go to S3-compatible object storage (MinIO). The bucket allows anonymous
  reads but not listing; object keys are UUIDs. The file type is decided by its
  bytes (magic numbers), never by its name or the browser's Content-Type; SVG
  and HTML are refused because they can carry scripts. Photos (JPEG, PNG, WebP,
  HEIC) are re-encoded to WebP without metadata, because a phone photo carries its
  GPS position in EXIF. Identical bytes are stored once. GeoJSON is accepted for
  map layers only after it parses as GeoJSON. The object is written
  before its row (a row never points at nothing) and deleted after it (a failure
  leaves an orphan object, never a broken link).

## Content

- Nine kinds share one model: profile, experience, project (`portfolio` or
  `lab`), education, certificate, study, writing, post, skill. Each kind has a
  small schema for its structured fields (dates, organization, links); unknown
  fields are rejected. The admin form is generated from `GET /admin/content/kinds`.
- Rich text is TipTap JSON, validated against an allow-list of nodes, marks and
  attributes. HTML is rendered on the server with everything escaped; images
  may only point at our own storage. Links are http(s), mailto or a path on the
  site.
- Case studies need more than prose, so the document can hold structured blocks
  (gallery, metrics, diagram, logo wall, timeline, map…), each validated by a
  small schema. The API sends the body as HTML runs between blocks, and the site
  renders each kind with its own component. A block can be hidden: it stays in
  the document for the author and never leaves the server, in any form (API, MCP,
  search index). Content stays out of the repository: blocks are data, like text.
- `draft` or `published`. Publishing needs both languages. Only published
  content produces events, and every event carries the entry version so a
  consumer can ignore stale deliveries.
- Optimistic concurrency: every write sends the version it edited; a stale one
  gets 409 with the current version.
- At most one profile, enforced by the use case and by a partial unique index.

## Contacts

- `POST /api/contact` is public and documented in the OpenAPI schema so agents
  can find it. It is rate limited per client (5/day, keys are HMACs of the IP),
  honours `Idempotency-Key`, and has a honeypot field for naive bots.
- Emails go out from the worker, never from the request: one to the owner, and
  a fixed-template thank-you to the sender when they left an email. The
  thank-you never echoes what the visitor typed, and goes to the same address at
  most once a day, decided from what was actually sent, so a failed send never
  uses up the quota. Each send is committed on its own, so a redelivery does not
  repeat the previous one.

## Identity

- A single admin, email + password hashed with Argon2. There is no sign-up
  route: the admin is created from the CLI (`make create-admin`).
- Server-side sessions: the cookie carries a random token, the database stores
  only its SHA-256. Cookie is `HttpOnly`, `Secure`, `SameSite=Strict`. A
  session is revocable by deleting its row, which a JWT would not allow.
- Progressive lockout after repeated failed logins. Unknown emails still run a
  password verification so response time does not reveal which emails exist.
- Admin routes are excluded from the public OpenAPI schema. Hiding them is not
  the protection; authentication is.

## Search

- Hybrid retrieval in Qdrant: dense vectors plus BM25 sparse vectors, with a
  language-specific stemmer and a `lang` filter (BM25 does not work across
  languages). If dense retrieval fails, search degrades to BM25 only.
- Dense embeddings come from an API: `openai/text-embedding-3-small` (1536
  dimensions, cosine) through OpenRouter. The in-process multilingual MiniLM it
  replaced truncates at 128 tokens, about half of a full chunk; this model reads
  up to 8191, and keeps the API process light on a small VPS. The eval checks the
  choice with recall@k and MRR.
- Chunks follow the semantic sections of the content (rich-text headings), not
  a fixed size. Content is curated, so its structure is the best boundary.

## Agent

- LangGraph orchestrates; it does not own the domain. Budget, grounding checks,
  prompt assembly and prompt registry are pure functions in `domain/`.
  LangChain types never cross into the domain.
- Flow: `route → retrieve → model ⇄ tools → guard → grounding → answer`; a
  failed check goes to `rewrite` once, and what still fails goes to `trim`.
  `route` is rules (small talk skips the lookups); the tools are
  `search_portfolio` and `read_case`.
- `retrieve` always puts a profile card first, as passage [1]: headline,
  summary, location, every job with its dates and what he is building now, one
  fact per line in the visitor's language. Who Erick is must not depend on how
  a question ranks.
- Two checks, cheapest first. `guard` is code: every number, technology and
  company in the answer must be in the passages (or the question), citations
  must point to real passages, the only email is Erick's. `grounding` is a
  second model reading claim by claim against every passage found; remarks
  about the site or about reaching Erick are filtered out in code, because
  verifiers flag them anyway.
- Nothing raw ever reaches the visitor. `rewrite` runs on the strong model with
  the exact reasons; `trim` drops only the flagged sentences and keeps the
  prose. With too little left, the answer points to Erick. An earlier version
  showed the passages themselves; it read like a database dump and was removed.
- Answers the site should give only when asked (why a job ended) are `note`
  blocks: indexed for search, never rendered, never in the public API.
- Stateless server: the client sends at most the last 6 turns.
- Prompts are `.md` files versioned by content hash; the hash goes into every
  trace.
- SSE streams step events with their detail, not tokens: the checks must see
  the whole answer before anyone does, and the site draws the trajectory.
- Models through OpenRouter: `gpt-oss-120b` answers (fast tier), `gpt-4.1-mini`
  checks and rewrites (strong tier), with `gpt-4o-mini` and Gemini 2.5 Flash as
  fallbacks. Measured on the dataset: `gpt-4o-mini` as the checker flagged facts
  the profile states word for word and let 97% drop to 89%; Gemini cost four
  times more for no fewer false flags; `gpt-4.1-mini` doubled the cost (still
  under US$ 0.001 per answer) and caught only real problems.
- A flagged claim whose parts each sit, word for word, on one line of a passage
  is dropped in code (`guard.supported`): a judge's false flag. A recombined
  fact ("CTO at Loopia") or an invented one ("a national award") is not on any
  line and stays flagged. Counts in words ("dozens" for 150) fail the code check.

## Observability and evals

- Langfuse v4 keeps only what arrives through OpenTelemetry: traces go as
  OTLP/HTTP JSON to `/api/public/otel/v1/traces`. The legacy ingestion API
  answers 207 and stores nothing (and shuts down on 2026-11-16 except for
  scores). `langfuse.*` attributes type each span (agent, retriever, tool,
  guardrail, generation) so Langfuse draws the same graph the site shows.
- `LANGFUSE_TRACING_ENVIRONMENT` separates the site (`production`), local runs
  and evals (`eval`).
- The dataset is public and versioned: `backend/evals/assistant.jsonl`,
  recruiter questions in Portuguese and English, small talk and adversarial
  cases (injection, prompt leak, off-topic, salary, phone, false premises,
  absence). It holds only what the site already publishes.
- `make eval` upserts the dataset and its items in Langfuse, runs every case
  through the real agent and makes each answer's trace an item of the run's
  experiment (Langfuse v4 reads `langfuse.experiment.*` on every span; the root
  span id is derived from the trace id so scores can point at it), then posts
  the scores in one batch. Checks are code: expected and forbidden terms,
  citations, which cases were read, whether it searched, no trim, grounded, no
  refusal. `first_pass` (no rewrite) is tracked, not required: a rewrite that
  fixes "more than 150" is the checks doing their job.
- The gate fails below 90% of cases passing, or on any forbidden term at all.

## Search (implemented)

- Search reads published content through a port (`SourceCatalog`) adapted over
  content, never through content's tables. Each entry and language becomes an
  overview chunk (summary, the names in its details such as the organization,
  tags) plus one chunk per heading section, packed to at most 1200 characters.
  Chunk ids are derived from (entry, language, position), so re-indexing
  overwrites instead of duplicating.
- Every content event (published, unpublished, deleted) runs the same use case:
  read the entry now and make the index match it. A stale or repeated event is
  harmless, which is what makes the consumer idempotent.
- Dense and BM25 vectors live in one Qdrant collection; Qdrant computes IDF and
  fuses both rankings with RRF. BM25 uses a Portuguese or English stemmer by the
  chunk's language, and every query is filtered by language.
- BM25 runs in-process (fastembed), loaded on first use in a thread. Only the
  dense side depends on the provider: a query gives up on it after 5 seconds and
  falls back to BM25, and indexing failures are retried by the worker's queue.

## MCP and agent-facing surfaces

- Remote MCP only (Streamable HTTP at `/mcp`, official SDK 2.x), mounted on the
  same FastAPI app and calling the same use cases as REST, so throttling applies
  to it too. Stateless with JSON responses: no session store, any worker can
  answer. No stdio package: the data lives on the server.
- DNS rebinding protection is off on purpose: it guards servers on localhost,
  and this one is public and unauthenticated by design.
- Expected domain errors (unknown slug, empty query, contact limit) reach the
  model with their message so it can correct the call; anything else stays
  opaque. Case studies go to the model as plain text, not HTML.
- Read-only tools carry `readOnlyHint`. `contact_erick` is the only write tool
  and asks the user for confirmation.
- `/AGENTS.md` and `/llms.txt` are generated from the database, so availability
  is never stale.
- Contact requests are rate limited, idempotent, never passed through an LLM,
  and deleted after 12 months by a daily job.

## Public API

- Read-only, published content only, one language per request, rich text
  already rendered to safe HTML. Contract in [`public-api.md`](public-api.md).
- Contexts stay independent: content declares an `AttachmentCatalog` port and
  the composition root plugs in an adapter over the files context.
- `/AGENTS.md`, `/llms.txt` and `/api/resume.json` (JSON Resume) are generated
  on every request from the same data, so availability is never stale. No LLM
  is involved.
- Public reads are cacheable for 60 s; anything under `/admin` is `no-store`.

## Site

- Two languages, one URL each: English at `/`, Portuguese under `/pt`
  (`/pt/work/rhye`, `/pt/mcp`). The URL decides the language, so links can be
  shared and every request asks the API for that `lang`. Fixed copy lives in
  `frontend/src/i18n/messages.ts`; content comes translated from the API.
- A visitor landing on an English URL goes to `/pt` when they chose Portuguese
  before, or when the browser asks for Portuguese and they never chose. The
  switch in the header remembers the choice in the browser.
- Light and dark themes: the system setting until the visitor picks one in the
  header. The CSS reads tokens (`--surface`, `--chip`…) that the dark theme
  redefines; nothing is themed by hand per component.
- The front page shows this site's own hybrid search running live
  (`/api/search/explain`), with the time of each step, instead of a decorative
  trace: a claim a technical reader can check. It runs once the cards are on
  screen, never on load.
- Animation is CSS with IntersectionObserver, no animation library, and it
  respects `prefers-reduced-motion`. Diagrams are SVG drawn from data, so they
  follow the theme and animate step by step.
- The space-syntax map comes from `tools/space_syntax.py`, run offline on open
  OpenStreetMap data; the layer is a file in our storage, not code.

## Limits

- 10 requests/s per IP on the API (token bucket, burst 20, in process memory:
  per-second limits must be cheap). Limits counted in days live in Postgres. Chat: 30 messages/min and 150/day per IP,
  Turnstile, and a global monthly LLM budget circuit breaker.

## Infrastructure

- One VPS running Easypanel. Frontend and backend build with Nixpacks
  (`nixpacks.toml` in each app).
- No Docker locally: the app runs with `uv` and connects through `.env` to the
  services on the VPS.
- Integration tests create one temporary database per test session, shared by
  all integration tests, with each test rolled back.

## Quality

- `ruff`, `mypy --strict`, `pytest` with 100% coverage, `import-linter`. All of
  it runs with `make check`.

## Delivery order

1. Foundation: monorepo, `make`, `identity`, `create-admin`.
2. Content and admin: rich text, attachments, draft/published, outbox, contacts.
3. Public REST API and frontend v1 with real data, `/AGENTS.md`.
4. Hybrid search and MCP.
5. Agent and evals.
6. Status page, "My MCP" page, MCP Registry.
