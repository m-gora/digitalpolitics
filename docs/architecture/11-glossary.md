# 11. Glossary

| Term | Meaning |
|---|---|
| **Gliederung** | A party unit (e.g. Landesverband LV, Bezirksverband BV, Ortsverein OV). Exists only as a slug in the config registry, never as a database row (arch-02) |
| **District slug** | Stable string identifier of a Gliederung (e.g. `bv-friedrichshain-kreuzberg`). Add freely; never rename or remove while referenced (arch-02) |
| **District scope** | The set of slugs a user may write to: their groups claim expanded over the hierarchy (adr-03) |
| **Campaign** | A guided campaign-planning canvas anchored at a Gliederung, moving through the lifecycle Draft → Review → Running → Finished/Aborted → Archived (canv-02, canv-05) |
| **Canvas field** | One of the campaign plan fields grouped in Zieldefinition, Zielgruppen & Kanäle, and Material, Organisation & Storytelling. Data Harvest is the privacy-sensitive exception (canv-02, adr-04) |
| **Initiative** | A group of campaigns coordinated around a shared narrative, anchored at a fixed Gliederung; has AI-assisted domain/narrative coherence scores and at most one outlier candidate (canv-01, adr-06) |
| **Fork / template forking** | Copying a campaign's canvas field answers into a new Draft; placement and data are not copied (canv-03) |
| **Retrospective** | Post-mortem auto-created when a campaign finishes or is aborted (canv-04) |
| **Questionnaire** | An ordered set of 1–5 questions for citizens; statuses Draft → Active ⇄ Closed; at most one linked campaign (crowd-01) |
| **Respondent app** | The anonymous kiosk-style PWA at `/crowd/r/{token}`; offline-capable via service worker + IndexedDB (crowd-02) |
| **Response** | An anonymous questionnaire answer: client UUID (idempotency key), coarsened location, scrubbed answers; no identifiers (crowd-03) |
| **Scrubbing** | Deterministic server-side regex replacement of PII in free text before storage (crowd-03) |
| **Voice transcription** | Gemini (Google) transcription of citizen voice input; audio processed in memory, never stored (crowd-04, adr-07) |
| **Forward auth** | Proxy pattern: Traefik calls oauth2-proxy per request and relays trusted identity headers to the app (arch-01) |
| **Groups claim** | OIDC claim `https://dpp/groups` injected by an Auth0 Action from `app_metadata.gliederungen` (adr-03) |
| **SSE** | Server-Sent Events; per-module channels with defined event catalogs; refetch-on-reconnect (arch-03) |
| **TypeSafe / Jev** | System One decision service used for rubric (`Score`) and `Choice` judgements in coherence scoring (adr-06) |
| **Flux** | GitOps controller reconciling `k8s/app/` into the cluster, with SOPS decryption (k8s/README.md) |
| **SOPS** | Git-encrypted secrets (age key in cluster); only `data`/`stringData` fields encrypted (k8s/README.md) |
| **Semantic release** | Conventional-commit-driven versioning in the release workflow; images build only on `app/**` changes |
