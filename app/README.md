# Digital Politics Platform — Campaign Canvas prototype

Prototype implementation of the Campaign Canvas module (see `../spec/02-modules/canv-*.md`),
built per `../spec/01-adrs/adr-01.md` (FastAPI + htmx + SSE + Postgres/pgvector/postgis).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package/venv manager)
- Docker (for the local Postgres instance)
- The [Tailwind CSS standalone CLI](https://tailwindcss.com/blog/standalone-cli) (no Node.js needed):

  ```sh
  mkdir -p bin
  curl -sL -o bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
  chmod +x bin/tailwindcss
  ```

  (swap `macos-arm64` for your platform's asset name if different)

## First-time setup

```sh
cp .env.example .env          # fill in OPENAI_API_KEY if you want real coherence scores
docker compose up -d db       # Postgres 16 with postgis + pgvector extensions
uv sync                       # install Python dependencies
uv run alembic upgrade head   # create the schema
uv run python -m dpp.seed     # example hierarchy + campaigns (idempotent)
./bin/tailwindcss -i src/dpp/static/css/input.css -o src/dpp/static/css/output.css
```

## Running

```sh
uv run uvicorn dpp.main:app --reload
```

Open http://localhost:8000. In development (`APP_ENV=development`, the default), a yellow
dev bar lets you "log in" as one of a few fixed personas anchored at different points in the
seeded hierarchy — this simulates the forward-auth headers a real proxy would set (arch-01),
including hierarchical write-access inheritance (adr-03):

| Persona | Anchored at | Can write to |
|---|---|---|
| Anna Berg | LV Berlin | everything |
| Jonas Krüger | BV Friedrichshain-Kreuzberg | BV F-K + OV Kreuzberg + OV Friedrichshain |
| Mira Noll | OV Kreuzberg | only OV Kreuzberg |
| Peter Sailer | BV Mitte | BV Mitte + OV Wedding |

This impersonation bar and its middleware (`dpp.auth.dev_impersonation`) are only wired up
when `APP_ENV=development` — never in a real deployment.

While developing the frontend, run Tailwind in watch mode in a second terminal:

```sh
./bin/tailwindcss -i src/dpp/static/css/input.css -o src/dpp/static/css/output.css --watch
```

## Tests

Tests run against a real Postgres database (`dpp_test`, created automatically on the same
`docker compose` instance) since the schema relies on the `pgvector` extension.

```sh
docker compose up -d db
uv run pytest
```

## Project layout

Organized by bounded context rather than by technical layer: `campaign/` is the single
domain package covering everything in `spec/02-modules/canv-*` (hierarchy, campaign canvas,
lifecycle, forking, retrospectives, initiatives + coherence score). `auth/` and `sse.py` are
shared infrastructure used by that domain, not domains themselves.

```
src/dpp/
  config.py, db.py, templating.py   settings, async SQLAlchemy engine/session, Jinja2 setup
  main.py                            FastAPI app factory + the friendly-401-page handler
  sse.py                             generic SSE pub-sub mechanism (Channel/Event), reusable
                                      by whatever module comes next (arch-03)
  auth/                              forward-auth header parsing, RBAC, dev impersonation
    headers.py, dependencies.py, dev_impersonation.py, router.py (dev-only /_dev/* routes)
  campaign/                          THE bounded context (spec/02-modules/canv-01..05)
    models.py                        District, Campaign, CampaignStatus, Initiative,
                                      InitiativeCampaign, Retrospective
    hierarchy.py                     district tree + expand_district_scope (adr-03)
    lifecycle.py                     Zieldefinition->Zielgruppen & Kanäle->Material/Organisation/Storytelling gating, transitions, fork
    membership.py                    initiative create/add/remove-member, queries
    coherence.py                     embeddings + cosine similarity + recompute orchestration
    events.py                        the "canvas" SSE channel + publish_* helpers
    router.py                        all HTTP routes: /districts, /campaigns, /initiatives,
                                      /events/canvas
  templates/, static/                Jinja2 + htmx + Tailwind (centralized, not per-domain)
  seed.py                            example data
migrations/                          Alembic
tests/                                pytest + httpx, real Postgres
```

## What's implemented

- Arbitrary-depth district hierarchy (canv-01).
- Guided campaign creation wizard: district selection → Zieldefinition → Zielgruppen & Kanäle
  → Material, Organisation & Storytelling, with the canv-02 guiding questions shown beside
  each field. Boosted htmx navigation and visible request feedback keep step changes responsive.
- Campaign canvas with gated Zieldefinition → Zielgruppen & Kanäle → Material, Organisation &
  Storytelling fields (canv-02), last-write-wins
  concurrency with SSE live-refresh (arch-03).
- Full lifecycle: Draft → Review → Running → Finished/Aborted → Archived (canv-05).
- Template forking (canv-03): copies canvas field answers only.
- Post-mortem retrospective, auto-created on Finished/Aborted (canv-04).
- Initiatives scoped to a single district, with an AI-assisted coherence score computed
  from OpenAI embeddings of the narrative fields (canv-01, adr-04). Without
  `OPENAI_API_KEY` set, the app still runs — coherence scores just stay "n/a".
- District-scoped RBAC with hierarchical inheritance via pre-expanded `X-District-Scopes`
  (arch-02, adr-03); read access is global for any authenticated user.

## Known prototype-scale limitations

- SSE is a single in-process channel (`dpp.campaign.events`, using `dpp.sse`) — works for one worker process
  only, and does not replay missed events on reconnect (arch-03 accepts this for v1).
- No real forward-auth proxy; `dpp.auth.dev_impersonation` stands in for local development.
- Field-level edit conflicts are last-write-wins with no locking.
