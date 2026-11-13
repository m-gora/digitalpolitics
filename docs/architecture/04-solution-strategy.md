# 4. Solution Strategy

The overall strategy: **one server-rendered monolith, small surface area, privacy concentrated in one module, operations by GitOps.** Each key decision is recorded in an ADR in `spec/01-adrs/`; the table summarizes the strategy and points there for the binding rationale.

| # | Decision | Where | Why (short) |
|---|---|---|---|
| 1 | Monolith with bounded contexts instead of services | adr-01 | Single developer, single cluster; module boundaries carried by package structure |
| 2 | Server-rendered Jinja2 + htmx + SSE, no SPA | adr-01 | Interactivity via swaps and partial refreshes; no client framework, build tooling stays minimal |
| 3 | Forward-auth proxy pattern: Traefik → oauth2-proxy sidecar → trusted headers | arch-01, adr-03 | Identity handled by proven components; the app never sees a login page and trusts headers only from the proxy network |
| 4 | District scopes resolved in the app from the groups claim | adr-03 | Hierarchy logic lives in one place (the Gliederung config registry); proxy stays dumb; read global, write scoped (arch-02) |
| 5 | Gliederung tree as config file, not database rows | arch-02, adr-03 | Rarely changes, not user-editable; slugs as stable identifiers; no FK, write check itself validates slugs |
| 6 | SSE per module channel, refetch-on-reconnect | arch-03 | Simple pub-sub (`dpp.sse`), no event log; concurrent canvas edits get refreshed views |
| 7 | Privacy by design for citizen data | arch-04, crowd-03 | Anonymity, server-side PII scrubbing, coordinate coarsening, no identifiers stored |
| 8 | AI as optional, swappable capability | adr-04, adr-05, adr-06 | Provider abstraction (`AI_PROVIDER`), TypeSafe rubric scoring for coherence; app fully usable without any API key |
| 9 | Voice transcription as narrow, explicit exception | adr-07 | Audio sent for transcription only, never stored; public path allow-list is explicit |
| 10 | PostGIS + vendored Leaflet for geospatial | adr-08 | Fits the no-build-step approach; GiST-indexed geography columns |
| 11 | GitOps deployment, image built only on app-code changes | k8s/README.md, `.github/workflows/release.yml` | Infra-only changes don't produce releases; flux reconciles config changes without image rebuilds |
| 12 | Single tenant, hard-coded design | adr-02, arch-07 | No theming machinery for one party |

## Strategy consequences worth knowing

- **The app is usable without any external AI**: missing keys leave summaries/scores empty rather than failing (adr-05, adr-06).
- **Everything read-only is global**: any authenticated user reads any district's campaigns, questionnaires and analysis; this is what makes forking and knowledge retention work (arch-02, canv-03).
- **The crowdsourcing module is the privacy hotspot**: it is the only component with a public surface, and its privacy rules (scrubbing, coarsening, idempotent offline sync) are specified independently of the rest (crowd-02, crowd-03).
- **Concurrency is deliberately simple**: last-write-wins field saves + SSE refresh (arch-03); no distributed locking, no event sourcing.
