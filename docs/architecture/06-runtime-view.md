# 6. Runtime View

## 6.1 Authenticated page request (forward-auth chain)

```mermaid
sequenceDiagram
    autonumber
    actor U as Campaigner
    participant T as Traefik Gateway
    participant O as oauth2-proxy (sidecar)
    participant A as dpp app
    participant DB as PostgreSQL

    U->>T: GET /campaigns/42
    T->>O: forwardAuth request
    O->>U: redirect to Auth0 (if no session)
    U->>O: Auth0 login callback
    O->>T: 200 + auth response headers
    Note over O,T: X-User-Id (OIDC sub),<br/>X-Auth-Request-Groups (https://dpp/groups claim),<br/>preferred username, email
    T->>A: request + trusted headers
    A->>A: auth.headers.parse_identity:<br/>expand groups → district_scopes (adr-03)
    A->>DB: query campaign 42 (read = global)
    A-->>U: rendered page
```

Key points: the app never performs a login and trusts the headers only because it is unreachable except through the proxy chain (arch-01). Write operations additionally run `Identity.has_write_access(district_slug)` against the expanded scope set (arch-02, adr-03). Membership changes in Auth0 take effect at the next login/token refresh.

## 6.2 Concurrent canvas editing (SSE)

```mermaid
sequenceDiagram
    autonumber
    actor U1 as User A
    actor U2 as User B
    participant A as dpp app
    participant S as SSE channel "canvas"

    U1->>A: GET /events/canvas (EventSource)
    A->>S: subscribe
    U2->>A: htmx POST field save (campaign.field_updated)
    A->>DB: last-write-wins update
    A->>S: publish field_updated
    S-->>U1: event → htmx refetch of the field
    Note over U1: view refreshed,<br/>no stale overwrite
```

The client refetches current state on reconnect; there is no event replay or offset tracking in v1 (arch-03). Status transitions and AI outputs publish `campaign.status_changed` and `campaign.summary_updated` on the same channel; the crowd module uses a separate `crowd` channel.

## 6.3 AI follow-ups (summary, coherence)

```mermaid
sequenceDiagram
    autonumber
    actor U as Campaigner
    participant A as dpp app
    participant AI as AI provider / TypeSafe
    participant DB as PostgreSQL

    U->>A: complete last canvas field / edit campaign
    A->>DB: store field
    A-->>U: response (summary not ready yet)
    A->>AI: background task<br/>canvas fields except Data Harvest (adr-04)
    AI-->>A: summary or rubric scores
    A->>DB: store summary / 0..1 scores + outlier
    A->>A: publish summary_updated / coherence_updated
```

Without a configured key the app simply skips the call — outputs stay empty and everything remains usable (adr-05, adr-06). Scores are heuristic LLM judgements; a failed recompute keeps previous values.

## 6.4 Anonymous respondent flow

```mermaid
sequenceDiagram
    autonumber
    actor C as Citizen
    participant T as Traefik Gateway
    participant A as dpp app
    participant AI as Gemini (transcription)
    participant DB as PostgreSQL
    participant IDB as IndexedDB (device)

    C->>T: GET /crowd/r/{token}
    Note over T: public allow-list (adr-07),<br/>no forward-auth
    T->>A: request (no identity headers)
    A-->>C: start screen: privacy notice, GPS prompt
    C->>A: POST /crowd/api/r/{token}/transcribe (optional)
    A->>OAI: audio, language hint de
    OAI-->>A: transcript (in memory only, never stored)
    A-->>C: editable text inserted
    C->>A: POST response {client UUID, answers, lat/lon/accuracy}
    A->>A: validate vs questionnaire, scrub PII,<br/>round coordinates to ~10 m, rate-limit by IP
    A->>DB: insert response + answers
    A-->>C: thank-you screen, auto-reset
    Note over C,IDB: offline: page cached by service worker,<br/>response buffered in IndexedDB,<br/>synced idempotently on reconnect
```

Late-synced offline responses are accepted only if `captured_at` falls inside the questionnaire's collection window; anything else is rejected with 410 and discarded by the client (crowd-03). `crowd.response_received` is published with questionnaire id and count only.

## 6.5 Campaign lifecycle and questionnaires

```mermaid
stateDiagram-v2
    [*] --> Draft: create / fork
    Draft --> Review: submit (write access)
    Review --> Draft: send back
    Review --> Running: promote
    Running --> Finished: close
    Running --> Aborted: abort
    Finished --> Archived
    Aborted --> Archived
```

Transitioning to `Finished`/`Aborted` auto-creates the retrospective (canv-04) and closes linked Active questionnaires (crowd-01). Questionnaires have their own lifecycle (`Draft → Active ⇄ Closed`); activation of a linked questionnaire is only possible while the campaign is `Running`. Every transition publishes `campaign.status_changed` / `crowd.questionnaire_status_changed`.
