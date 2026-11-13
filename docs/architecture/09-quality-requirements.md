# 9. Quality Requirements

## Quality model for this system

Priorities (from [01-introduction-and-goals.md](01-introduction-and-goals.md)) in arc42's usual terms: **data integrity/privacy** first, then **maintainability/operability**, then functional enrichment.

## Privacy (top priority)

| Requirement | How it is met | Source |
|---|---|---|
| Citizen responses are anonymous | No identity, IP, device or user-agent stored; no link from response to person; IPs only transiently in memory for rate limiting | crowd-03 |
| No PII in stored text | Deterministic server-side regex scrubber (email, phone incl. `+49`/`0049`/`0xx`, URLs, street addresses) before insert | crowd-03 |
| Coarse location only | Coordinates rounded server-side to 4 decimals (~10 m); exact fixes never reach the DB | crowd-03 |
| Minimal AI exposure | Campaign canvas fields except Data Harvest go to external AI; citizen answers, transcripts and locations never leave except voice audio for transcription-only (never stored) | adr-04, adr-07 |
| Informed consent | Non-skippable privacy notice before the first answer, covering anonymity, location saving and external transcription (crowd-03) | crowd-03 |

## Operational quality

| Scenario | Requirement |
|---|---|
| Deploy a config change | `git push` → flux reconciles within 10 min; ConfigMap hash rolls the pod; no manual kubectl |
| Deploy an app change | semantic-release cuts a version, GHCR image is built for amd64/arm64, dependabot bumps the pinned tag, flux applies; migrations run automatically in the initContainer |
| Infra-only change | Must **not** produce a release/image (paths-filtered workflow) |
| Rebuild the cluster | Postgres from infra repo + `flux create` (two imperative commands) + SOPS secrets from git |
| Degraded AI | Missing/failing API keys leave outputs empty; the app stays fully usable |
| Liveness | `/healthz` served unauthenticated by the app; container probes call it directly on the Service (k8s/README.md also lists a healthz HTTPRoute that bypasses forward-auth — not yet present in `k8s/app/`) |

## Testability

- pytest with **real Postgres** (not SQLite): exercises generated `tsvector` columns, PostGIS geography, check constraints (crowd ingest, questionnaire limits).
- Test suite spans RBAC and scope resolution, lifecycle gating, forking, crowdsourcing privacy/ingest rules, transcription fallbacks, health.
- CI validates k8s manifests via `kubectl kustomize` + client-side dry-run on every change.

## Usability

- German UI, guided campaign wizard with sequential gating (canv-02), guiding questions beside each field.
- Kiosk-style respondent app: fullscreen, one question per screen, ≥48 px targets, auto-reset for device handoff, offline-capable (crowd-02).
