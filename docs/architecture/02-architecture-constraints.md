# 2. Architecture Constraints

## Technology constraints

| Constraint | Source |
|---|---|
| FastAPI (Python) backend, server-rendered Jinja2 + htmx frontend, no SPA build | adr-01 |
| Tailwind CSS with hard-coded party brand tokens (Public Sans, FDP colors) | adr-01, arch-07 |
| PostgreSQL with `postgis`; `pgvector` retained only for legacy migration columns | adr-01, adr-06 |
| Real-time via Server-Sent Events, not WebSockets | adr-01, arch-03 |
| Single tenant, one party, German-only UI (no i18n) | adr-02, arch-06 |
| User-facing German; source code and docs in English | arch-06 |

## Organizational / operational constraints

| Constraint | Source |
|---|---|
| GitOps on a personal k3s cluster; Postgres and cluster plumbing live in a separate infra repo (`m-gora/cluster-config`) | k8s/README.md |
| App code, including k8s manifests, in this repository; deployed as one Flux Kustomization | k8s/README.md |
| Auth0 as identity provider; an Auth0 Action injects Gliederung memberships as a namespaced groups claim | k8s/README.md, adr-03 |
| Secrets encrypted in git with SOPS (age key in cluster) | k8s/README.md |
| Container image built only on app-code changes, published to GHCR; dependabot bumps the pinned tag | `.github/workflows/release.yml`, k8s/README.md |
| One image tag used by both the migration initContainer and the app container | k8s/README.md |

## Legal constraints

| Constraint | Source |
|---|---|
| GDPR-relevant handling of citizen feedback: anonymity, no identifiers stored, PII scrubbing | arch-04, crowd-03 |
| Voice audio sent to Gemini (Google) for transcription is a documented narrow exception; data-protection review required | adr-07 |
| BFSG (accessibility) not required for internal tooling; open question for the public respondent surface | arch-06 |
| Data Harvest plans require an eventual legal basis / retention workflow (deferred) | canv-02 |

## Constraints that shape the design

The combination of *single developer*, *personal cluster* and *privacy-sensitive public surface* drives several decisions: the monolithic server-rendered architecture (adr-01), the forward-auth delegation to battle-tested components (Traefik + oauth2-proxy, arch-01), the config-file Gliederung tree instead of admin UIs (arch-02), and the explicit prototype-scale risk acceptance (adr-07, crowd-03).
