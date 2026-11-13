# 10. Risks and Technical Debt

Known and accepted — listed here so they are decisions, not surprises. Many are explicitly documented prototype-scale trade-offs in `spec/` and the READMEs.

## Technical debt

| Debt | Why it exists | Exit path | Source |
|---|---|---|---|
| Unused `pgvector` columns (`campaigns.domain_embedding`, `campaigns.narrative_embedding`) and the `vector` extension | Early migrations created them; coherence moved to TypeSafe (adr-06) | Squash migrations once history is stable, then drop extension | adr-06, app/README.md |
| Single-process SSE (`dpp.sse` in-process pub/sub) | Fine for one uvicorn worker | Redis/NATS pub-sub behind the same `Channel` interface | arch-03, app/README.md |
| No SSE event replay | Refetch-on-reconnect accepted for v1 | Client-side sequence offsets + short replay buffer if needed | arch-03 |
| Last-write-wins field concurrency | Deliberate simplicity for the canvas | Field-level version checks if real conflicts appear | arch-03 |
| Cosine-era migration artifacts (scores cleared, backfill needed) | adr-06 replaced embeddings | `python -m dpp.campaign.backfill_coherence` after upgrades | adr-06 |
| Duplicated Gliederung YAML (app config vs k8s ConfigMap) | Dev convenience vs deployment reality | Generate the k8s copy from the app copy in CI | k8s/README.md |
| Imperative Flux registration (etcd-only) | One-time setup simplicity | `flux export` into cluster-config for DR | k8s/README.md |

## Risks

| Risk | Mitigation (current) | Source |
|---|---|---|
| Person names not detected by the PII scrubber | On-screen respondent hints; documented v1 limitation | adr-07, crowd-03 |
| Anonymous endpoints are an abuse/cost surface | In-memory per-IP rate limits (30/min responses, 10/min transcription), 32 KB body cap, weak-secret tokens; closing the questionnaire is the remedy | crowd-03 |
| Google (Gemini) audio handling per API terms | Privacy notice discloses external transcription; flagged for the data-protection owner; transcription-only, audio never stored by the app | adr-07 |
| Campaign free text may contain accidental PII before leaving the app boundary | No detection in the prototype; user responsibility documented | adr-04 |
| Default OpenStreetMap tiles not suitable for production load | `MAP_TILE_URL` configurable; production source is an open item | adr-08 |
| Spoofed GPS / bot responses | Accepted for prototype; token + collection window are the only defenses | crowd-03 |
| Lost SOPS age key means manual secret re-entry | Key backed up in cluster and operator backup | k8s/README.md |
| Data Harvest legal basis / retention workflow undefined | Deferred to a future data-protection spec; field excluded from AI processing meanwhile | canv-02, adr-04 |
| BFSG applicability of the public respondent surface | Open legal question; pragmatic accessibility baseline maintained | arch-06 |
