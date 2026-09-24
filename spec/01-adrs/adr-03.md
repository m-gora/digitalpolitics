# ADR 03: Scope Header Resolution

## Context
arch-02 requires write access to be scoped by district, with access to a parent unit in the hierarchy (e.g. a Landesverband) implying access to all units beneath it (e.g. its Bezirksverbände and Ortsvereine).

## Decision
The forward-auth proxy / identity layer is responsible for resolving hierarchy inheritance. It sends the full, pre-expanded list of accessible district IDs (direct assignments plus all inherited descendants) in the `X-District-Scopes` header (see arch-01).

The backend does not compute inheritance. It only checks whether the target district ID of a write operation is present in the `X-District-Scopes` list.

## Consequences
- Hierarchy-traversal logic lives in one place (the identity/auth layer), not duplicated in the application.
- The backend's authorization check stays a simple list-membership check.
- Changes to a user's district assignment or to the hierarchy tree require the auth layer to recompute the expanded list on next login/token refresh.
- Read access is unaffected by this header: per arch-02, read access is global for any authenticated user.
