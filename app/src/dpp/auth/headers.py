"""Forward-auth header parsing. See spec arch-01 and adr-03.

The application trusts these headers only because it is assumed to be
deployed behind a forward-auth proxy that clients cannot bypass. In local
development, dpp.auth.dev_impersonation fabricates these same headers behind
an explicit APP_ENV=development gate.

Header names are env-configurable (DPP_USER_* variables) so the proxy layer
can be re-wired (e.g. k3s/Traefik instead of Caddy) without code changes.
X-User-Id remains the immutable identity key (the OIDC `sub` claim); the
display name is a separate, non-authoritative value resolved from the
oauth2-proxy X-Auth-Request-* headers.
"""

import os
from dataclasses import dataclass, field

from starlette.requests import Request

USER_ID_HEADER = os.environ.get("DPP_USER_ID_HEADER", "X-User-Id")
USER_ROLES_HEADER = os.environ.get("DPP_USER_ROLES_HEADER", "X-User-Roles")
DISTRICT_SCOPES_HEADER = os.environ.get("DPP_USER_DISTRICT_SCOPES_HEADER", "X-District-Scopes")
USER_NAME_HEADER = os.environ.get("DPP_USER_NAME_HEADER", "X-Auth-Request-Preferred-Username")
USER_EMAIL_HEADER = os.environ.get("DPP_USER_EMAIL_HEADER", "X-Auth-Request-Email")


@dataclass(frozen=True)
class Identity:
    user_id: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    # Pre-expanded set of accessible district IDs (direct + inherited), per adr-03.
    district_scopes: frozenset[str] = field(default_factory=frozenset)
    # Non-authoritative display name (first non-empty of name-ish header,
    # email header); may be None. See parse_identity.
    display_name: str | None = None

    def has_write_access(self, district_id: object) -> bool:
        return str(district_id) in self.district_scopes


def _split_header(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(v.strip() for v in value.split(",") if v.strip())


def _display_name(request: Request) -> str | None:
    return request.headers.get(USER_NAME_HEADER) or request.headers.get(USER_EMAIL_HEADER) or None


def parse_identity(request: Request) -> Identity | None:
    user_id = request.headers.get(USER_ID_HEADER)
    if not user_id:
        return None
    roles = _split_header(request.headers.get(USER_ROLES_HEADER))
    scopes = frozenset(_split_header(request.headers.get(DISTRICT_SCOPES_HEADER)))
    return Identity(
        user_id=user_id,
        roles=roles,
        district_scopes=scopes,
        display_name=_display_name(request),
    )
