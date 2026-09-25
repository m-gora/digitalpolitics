# ADR 01: Tech Stack

## Decision
- Backend: FastAPI (Python), matching the existing `app` scaffold.
- Frontend: server-rendered Jinja2 templates enhanced with htmx (no separate SPA build).
- Styling: Tailwind CSS, configured with the brand tokens from arch-07.
- Real-time updates: Server Sent Events (SSE) via `EventSource`, per arch-03.
- Database: PostgreSQL.
  - `pgvector` extension for embeddings used by initiative domain and narrative similarity scores (see canv-01).
  - `postgis` extension for future geospatial needs (e.g. the street feedback module referenced in arch-05).

## Consequences
- No client-side routing/state framework; interactivity is delivered via htmx swaps and SSE-triggered partial refreshes.
- Embedding-based similarity features live in the same database as transactional data; no separate vector store.
