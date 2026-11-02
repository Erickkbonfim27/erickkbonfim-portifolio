# Portfolio site

React + Vite + TypeScript port of the Claude Design handoff
(`erick-portfolio-handoff/`, kept out of the repository). The handoff CSS is in
`src/styles/handoff.css` verbatim; everything added on top lives in
`src/styles/app.css` and uses only the handoff's tokens.

## Data

Career data comes from the public API (contract: `../docs/public-api.md`):
availability, CV link, experience, learning cards, stack and the work-card text.
While it loads, or when the API is unreachable or has nothing published, each
section renders the handoff copy (`src/content/fallback.ts`), so the site always
looks complete. The bespoke work visuals and the rest of the copy are static.

Routes: `/` and `/work/:slug` (case study rendered from `GET /api/projects/{slug}`).
Anything else is the app's 404.

## Commands

```bash
npm install
npm run dev         # http://localhost:5173
npm run check       # typecheck + lint + tests
npm run build       # dist/
npm run preview     # serve dist/ locally
```

## Environment

| Variable | When | What |
|---|---|---|
| `VITE_API_URL` | build | API base URL, baked into the bundle (empty = same origin). Changing it needs a rebuild. |
| `API_ORIGIN` | runtime (Caddy) | API origin for the CSP `connect-src` and for proxying `/AGENTS.md` and `/llms.txt` |
| `FILES_ORIGIN` | runtime (Caddy) | file storage origin for the CSP `img-src` (images in case studies) |
| `PORT` | runtime | set by Easypanel; 3000 by default |

## Deploy

Easypanel builds with Nixpacks from `frontend/` (`nixpacks.toml`): `npm ci`,
`npm run build`, then Caddy serves `dist/` with the `Caddyfile`. Caddy adds the
security headers (CSP, nosniff, referrer and permissions policies, no framing),
caches hashed assets for a year and revalidates `index.html` on every visit.
