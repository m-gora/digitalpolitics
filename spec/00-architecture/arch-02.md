# Scope Based RBAC
Write access shall be protected and only allowed to members of the respective district (Gliederung).

Read access is global: any authenticated user may read any district's data. Only writes are scoped.

Access to a district implies access to all districts beneath it in the hierarchy (e.g. membership of a Landesverband grants write access to its Bezirksverbände and Ortsvereine). See adr-03 for how this inheritance is resolved.

## Gliederung as configuration
The Gliederung tree changes rarely and is not user-editable application data: it ships as a YAML file (`config/gliederungen.yaml`, injected into k3s via ConfigMap, path from `DPP_GLIEDERUNGEN_FILE`) and is loaded by `dpp.gliederungen` as the single source of truth for slugs, display names, and hierarchy.

The database stores no districts: campaigns and initiatives reference a `district_slug` plain string (indexed, no FK). Write-time validation comes from the scope check itself — a scope set is only ever built from registered slugs, so an invalid slug can never be written. Slugs may be added to the config freely; they must not be renamed or removed while data references them.

Users' district memberships come from Auth0 (`app_metadata.gliederungen`), injected into the token as the `https://dpp/groups` claim and relayed as `X-Auth-Request-Groups`; see adr-03.