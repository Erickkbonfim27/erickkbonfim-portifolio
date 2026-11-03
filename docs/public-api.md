# Public API

Read-only, unauthenticated, rate limited (10 requests/s per IP). Every content
endpoint takes `?lang=en|pt` (default `en`) and only ever returns published
content. Responses are cacheable for 60 seconds.

Base URL: `https://api.<domain>`. The OpenAPI schema is at `/openapi.json`.

## Shapes

```ts
type Lang = "en" | "pt";

type Link = { label: string; url: string };

type Attachment = {
  label: string;          // e.g. "CV"
  filename: string;       // name the browser saves it as
  url: string;            // direct download URL
  content_type: string;
  size: number;           // bytes
};

type SkillRef = { slug: string; title: string };

type Entry = {
  kind: "experience" | "project" | "education" | "certificate" | "study" | "writing";
  slug: string;
  title: string;          // role for experience, degree for education, name otherwise
  summary: string;
  tags: string[];
  details: Record<string, unknown>;  // kind-specific, see below
  body_html: string;      // sanitized HTML rendered on the server ("" when empty)
  body: Segment[];        // the same body in order: HTML runs and structured blocks
  skills: SkillRef[];
  attachments: Attachment[];
  published_at: string;   // ISO 8601
  updated_at: string;
};
```

`body` keeps the order of the document: `{ type: "html", html }` runs between
`{ type: "block", kind, data }` blocks. Kinds: `facts`, `metrics`, `gallery`,
`timeline` (`list` or `roadbook`), `diagram` (nodes, groups, edges and the steps that
walk through them), `logos`, `cases`, `quote` and `map` (a GeoJSON layer of our own
storage). Their schemas are in `backend/src/portfolio/contexts/content/domain/blocks.py`.
Images that are not in our storage, and hidden blocks, never reach the API.
`body_html` renders the blocks as plain HTML, for readers without components.

`details` by kind (every field optional unless marked):

| kind | fields |
|---|---|
| experience | `organization`*, `location`, `start`* (YYYY-MM), `end` (YYYY-MM, absent = current), `url`, `employment` |
| project | `collection`* (`portfolio` \| `lab`), `organization`, `start`, `end`, `state` (`active` \| `building` \| `standby` \| `shipped` \| `archived`), `links`: Link[] |
| education | `institution`*, `start`, `end`, `url` |
| certificate | `issuer`*, `issued` (YYYY-MM), `url` |
| study | `medium`* (`book` \| `course` \| `paper` \| `topic`), `author`, `url`, `progress` (`planned` \| `in_progress` \| `done`) |
| writing | `published` (YYYY-MM), `url` |

Lists are ordered by the position set in the admin, then most recent first.

## Endpoints

| Method and path | Returns |
|---|---|
| `GET /api/profile` | `Profile` (404 until a profile is published) |
| `GET /api/availability` | `Availability` |
| `GET /api/projects?collection=portfolio\|lab` | `Entry[]` |
| `GET /api/projects/{slug}` | `Entry` (404 if unknown) |
| `GET /api/experience` | `Entry[]` |
| `GET /api/education` | `Entry[]` |
| `GET /api/certificates` | `Entry[]` |
| `GET /api/studies` | `Entry[]` |
| `GET /api/writing` | `Entry[]` |
| `GET /api/writing/{slug}` | `Entry` |
| `GET /api/skills` | `Skill[]` |
| `GET /api/search?q=…&lang=&limit=&kind=` | `Hit[]`: hybrid search over published content (`limit` 1–20, default 5) |
| `GET /api/search/explain?q=…&lang=&limit=` | the same search step by step: `{ query, hits, dense, sparse, steps: {name, ms}[], degraded }` (`limit` default 3) |
| `GET /api/resume.json` | the CV in the [JSON Resume](https://jsonresume.org/schema) format |
| `POST /api/contact` | `202 { id }`, see below |
| `GET /AGENTS.md` | a brief for AI agents (markdown) |
| `GET /llms.txt` | an index for LLMs ([llms.txt](https://llmstxt.org)) |

```ts
type Profile = {
  name: string;
  headline: string;
  summary: string;
  bio_html: string;
  location: string | null;
  email: string | null;
  links: Link[];
  availability: Availability;
  attachments: Attachment[];   // the CV is the one labelled "CV"
};

type Availability = {
  status: "open" | "not_looking" | "unknown";   // unknown: no profile published yet
  open: boolean;
  updated_at: string | null;                    // YYYY-MM-DD
};

type Skill = {
  slug: string;
  title: string;
  category: "language" | "framework" | "ai" | "data" | "cloud" | "practice" | "tool";
  evidence: { kind: string; slug: string; title: string }[];  // where it was used
};
```

```ts
type Hit = {
  entry_id: string;
  kind: string;
  slug: string;
  title: string;    // the entry's title
  heading: string;  // the section the passage comes from ("" for the overview)
  text: string;     // the matching passage
  score: number;    // fused rank score, only meaningful within one response
};
```

## MCP

The same data as tools, for Claude, ChatGPT, Codex or any MCP client:
`https://api.<domain>/mcp` (Streamable HTTP, stateless, no authentication).

| Tool | |
|---|---|
| `get_profile`, `check_availability` | who, and whether open to work |
| `list_projects`, `get_project` | case studies (full text as plain text) |
| `get_resume` | JSON Resume |
| `search_portfolio` | hybrid search, with where each passage comes from |
| `get_skills` | skills with the work that used them |
| `list_studies` | what Erick is studying |
| `contact_erick` | the contact endpoint as a tool (asks the user to confirm) |

Prompts: `hire_erick(role, company)` and `career_story(lang)`.

### Contact

```http
POST /api/contact
Content-Type: application/json
Idempotency-Key: <optional, any unique string; retries with the same key return the same id>

{ "from": "Ana", "contact": "ana@company.com", "brief": "AI Engineer role, remote", "company": "Company", "lang": "en" }
```

`202 { "id": "<uuid>" }`. `422` on invalid input, `429` after 5 messages per day
from the same client. A hidden `website` field must stay empty (honeypot).
Contact data is used only to answer and is deleted after 12 months.

## Errors

`{ "detail": string }` with 404, 422 or 429. A 429 carries `Retry-After`.
