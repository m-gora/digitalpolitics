# Forward Auth
The application shall use the forward auth proxy pattern.
The following headers are used to send auth information to the backend:
- X-User-Id
- X-Auth-Request-Groups
- X-Auth-Request-Preferred-Username
- X-Auth-Request-Email

These headers are only trustworthy when received from the trusted forward-auth proxy network (oauth2-proxy as a sidecar of the dpp pod, relayed through Traefik's forwardAuth middleware). The application shall be deployed so that clients can never reach it directly and set these headers themselves.

Header names are configurable via environment (`DPP_USER_ID_HEADER`, `DPP_USER_GROUPS_HEADER`, `DPP_USER_NAME_HEADER`, `DPP_USER_EMAIL_HEADER`) so the proxy layer can be re-wired without code changes; the defaults above are canonical. `X-Auth-Request-Groups` is only sent by oauth2-proxy when the access token carries the configured groups claim (`OAUTH2_PROXY_OIDC_GROUPS_CLAIM=https://dpp/groups`), and Traefik relays only the headers explicitly listed in `authResponseHeaders`.

## Display name
`X-User-Id` carries the immutable identity key (the OIDC `sub` claim). A separate, non-authoritative display name is captured at write time from the headers the proxy relays from the IdP:

- `X-Auth-Request-Preferred-Username` (configurable via `DPP_USER_NAME_HEADER`)
- `X-Auth-Request-Email` (configurable via `DPP_USER_EMAIL_HEADER`)

The display name resolves to the first non-empty of the name-ish header, then the email header, else `None`. It is stored alongside the ID in `created_by_name` (campaigns, questionnaires) whenever a record is created or cloned — the clone/fork records the *acting* user's identity, never the source record's creator. Templates render `created_by_name`, falling back to the raw `created_by` ID for rows written before this existed. The display name is never used for authorization.

See adr-03 for how the groups claim resolves into district write scopes.

## Public routes
The crowdsourcing respondent routes (`/crowd/r/*`, `/crowd/api/r/*`) are deliberately public and never read these headers; see adr-07 and crowd-02.
