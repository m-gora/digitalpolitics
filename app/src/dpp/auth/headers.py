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

District scope resolution (adr-03) happens in the application, not the
proxy: the `groups` claim relayed as X-Auth-Request-Groups carries Gliederung
slugs (or "all"), which dpp.gliederungen expands per the arch-02 inheritance
rule. See dpp.gliederungen for the config source.
"""

import os
from dataclasses import dataclass, field

from starlette.requests import Request

import dpp.gliederungen as gliederungen

USER_ID_HEADER = os.environ.get("DPP_USER_ID_HEADER", "X-User-Id")
USER_NAME_HEADER = os.environ.get("DPP_USER_NAME_HEADER", "X-Auth-Request-Preferred-Username")
USER_EMAIL_HEADER = os.environ.get("DPP_USER_EMAIL_HEADER", "X-Auth-Request-Email")
USER_GROUPS_HEADER = os.environ.get("DPP_USER_GROUPS_HEADER", "X-Auth-Request-Groups")


@dataclass(frozen=True)
class Identity:
    user_id: str
    # Reserved for future role concepts (e.g. a role:* group-prefix
    # convention over the groups claim); never populated today.
    roles: tuple[str, ...] = field(default_factory=tuple)
    # Expanded set of accessible district slugs (Gliederung groups expanded
    # per the arch-02 inheritance rule). Write access is membership here.
    district_scopes: frozenset[str] = field(default_factory=frozenset)
    # Non-authoritative display name (first non-empty of name-ish header,
    # email header); may be None. See parse_identity.
    display_name: str | None = None

    def has_write_access(self, district_slug: str) -> bool:
        return district_slug in self.district_scopes


def _split_header(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(v.strip() for v in value.split(",") if v.strip())


def _display_name(request: Request) -> str | None:
    return request.headers.get(USER_NAME_HEADER) or request.headers.get(USER_EMAIL_HEADER) or None


def _district_scopes(groups: tuple[str, ...]) -> frozenset[str]:
    scopes: set[str] = set()
    for group in groups:
        scopes |= gliederungen.expand(group)
    return frozenset(scopes)


def parse_identity(request: Request) -> Identity | None:
    user_id = request.headers.get(USER_ID_HEADER)
    if not user_id:
        return None
    groups = _split_header(request.headers.get(USER_GROUPS_HEADER))
    return Identity(
        user_id=user_id,
        district_scopes=_district_scopes(groups),
        display_name=_display_name(request),
    )
