# ADR 03: District Scope Resolution (groups claim)

> Supersedes the original "X-District-Scopes header" decision (proxy-side
> pre-expansion of district IDs). Re-recorded during the k3s migration: the
> Gliederung tree moved from the database to a config file, and the district
> identifier changed from UUIDs to slugs.

## Context
arch-02 requires write access to be scoped by district (Gliederung), with access to a parent unit in the hierarchy (e.g. a Landesverband) implying access to all units beneath it (e.g. its Bezirksverbände and Ortsvereine).

The Gliederung tree is deployment configuration, not user-editable application data (see arch-02): it ships as a YAML file via ConfigMap and is loaded by `dpp.gliederungen` as an immutable in-memory registry. Campaigns and initiatives store the district as a plain `district_slug` string; there is no districts table.

Users' district memberships live in Auth0 (`app_metadata.gliederungen`: a slug or `"all"`), injected into the token as the namespaced `https://dpp/groups` claim by an Auth0 Action. oauth2-proxy relays it as `X-Auth-Request-Groups`, which it only emits when `OAUTH2_PROXY_OIDC_GROUPS_CLAIM` is configured, and Traefik only forwards because the header is listed in `authResponseHeaders`.

## Decision
The application resolves district scopes itself, from the groups claim:

1. `dpp.auth.headers.parse_identity` reads `X-Auth-Request-Groups` (comma-separated group values) and expands each group via `dpp.gliederungen.expand`: a Gliederung slug expands to the slug plus all its descendants (the arch-02 inheritance rule, computed from the config registry); `"all"` expands to every registered slug; unknown groups contribute nothing.
2. The resulting `district_scopes` frozenset is attached to the `Identity`; the write check (`Identity.has_write_access(district_slug)`, used by `ensure_write_access`) is a plain membership test against it.
3. The proxy performs no hierarchy logic; it only relays the raw claim.

There is no separate `X-District-Scopes` header and no `X-User-Roles` header (roles were never consumed; a future role concept can reuse the groups channel, e.g. a `role:*` prefix convention).

## Consequences
- Hierarchy-traversal logic lives in one place (the config registry), and the same code path serves production and dev impersonation (dev personas carry a `group` instead of fabricating pre-expanded scopes).
- Authorization is enforced purely at write time; because the scope set is built from the registry, an invalid slug can never pass the write check — no FK to a districts table is needed. Operational rule: slugs may be added to the config freely but must not be renamed or removed while data references them.
- Membership changes made in Auth0 take effect on the next login/token refresh (oauth2-proxy revalidates the session); config changes roll the pods via the ConfigMap hash.
- Read access is unaffected: per arch-02, read access is global for any authenticated user.
- Header names are env-configurable (see arch-01) so the proxy layer can be swapped without code changes.
