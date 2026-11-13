# 8. Cross-cutting Concepts

## Authentication: forward-auth headers

Identity enters the app exclusively as headers injected by the trusted proxy chain (Traefik → oauth2-proxy sidecar): `X-User-Id` (immutable OIDC `sub`), `X-Auth-Request-Groups`, `X-Auth-Request-Preferred-Username`, `X-Auth-Request-Email`. Header names are env-configurable (`DPP_USER_ID_HEADER`, …) so the proxy layer can be re-wired without code changes (arch-01). In `APP_ENV=development` only, a middleware and `/_dev/*` routes simulate these headers with fixed personas.

## Authorization: district-scoped writes, global reads

- **Read:** any authenticated user reads everything (campaigns, questionnaires, analysis).
- **Write:** allowed only for districts the user's groups claim covers, expanded hierarchically. The expansion happens **in the app** (`dpp.gliederungen.expand`): a slug expands to itself plus all descendants; `"all"` expands to every slug; unknown groups contribute nothing. The write check is a set membership test — because scopes are built only from registered slugs, an invalid slug can never be written, which is why the DB needs no districts table or FK (arch-02, adr-03).
- **Creator attribution** is separate: `created_by` (immutable id) plus `created_by_name` (display name captured at write time, never used for authorization). Forks record the acting user, not the source creator (arch-01).
- **Crowd module:** only the creator may edit/activate/close/delete a questionnaire; linking one to a campaign requires write access to that campaign's district (crowd-01).

## Configuration

| What | Where |
|---|---|
| Env settings (`config.py`, `get_settings`) | `APP_ENV`, `AI_PROVIDER`, header names, file paths, model names, map tile URL |
| Gliederung tree | `app/config/gliederungen.yaml` (bundled for dev) / `k8s/app/gliederungen.yaml` (deployed) — **keep in sync** |
| AI keys | `OPENAI_API_KEY` / `GOOGLE_API_KEY` (summaries via `AI_PROVIDER`, transcription via `GOOGLE_API_KEY`), `TYPESAFE_API_KEY`; absence degrades gracefully to "no AI output" |

## Events (SSE)

One channel per module (`canvas`, `crowd`), defined catalogs of events (arch-03): `campaign.field_updated`, `campaign.status_changed`, `campaign.summary_updated`, `initiative.updated`, `initiative.coherence_updated`; `crowd.questionnaire_status_changed`, `crowd.response_received`. Reconnect = refetch, no replay. `crowd.response_received` deliberately carries no location or content.

## Error handling

FastAPI exception handler renders a friendly HTML 401 page for browser navigations (with the dev impersonation bar where applicable) while keeping JSON errors for SSE/htmx/API requests (`main.py`). Crowd ingest errors are status-coded for the client: 410 for out-of-window/questionnaire-gone, validation errors per crowd-03.

## Database and migrations

- Alembic migrations run as an **initContainer** at every pod start (idempotent), not as k8s Jobs (k8s/README.md).
- Postgres-specific features are embraced: generated `tsvector` search columns, UUIDs, PostGIS geography with GiST index, check constraints (e.g. 1–5 questions per questionnaire).
- Tests run against a real Postgres (`db/Dockerfile` provides the extension-enabled image) precisely because of these features.

## Internationalization and design

German-only, no i18n machinery (arch-06). Design tokens (FDP colors #FFE000/#032D67/#00A7E7, Public Sans) are hard-coded Tailwind config from arch-07; the respondent app uses its own minimal base template and separately built CSS so the admin stylesheet is untouched.

## Accessibility

No formal WCAG/BFSG compliance for internal surfaces (arch-06). The respondent app maintains a pragmatic baseline: ≥48×48 px targets, labelled controls, keyboard/screen-reader operable (crowd-02); BFSG applicability for the public surface remains an open legal question.
