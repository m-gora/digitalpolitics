"""Dev-only forward-auth header simulation.

There is no real forward-auth proxy in local development. This module lets a
developer pick a persona from a small fixed list and fabricates the same
X-User-Id / X-User-Roles / X-District-Scopes headers a real proxy would send
(see arch-01, adr-03). It is only ever wired up when APP_ENV=development
(see dpp.main); it must never run in a real deployment, since it would let
any client set its own identity.
"""

from dataclasses import dataclass
from http.cookies import SimpleCookie

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from dpp.auth.headers import DISTRICT_SCOPES_HEADER, USER_ID_HEADER, USER_ROLES_HEADER

IMPERSONATION_COOKIE = "dpp_dev_identity"


@dataclass(frozen=True)
class DevPersona:
    id: str
    label: str
    anchor_district_name: str
    roles: tuple[str, ...] = ("member",)


# Matches the seed data in dpp.seed. Each persona is anchored at a district;
# their effective X-District-Scopes is that district + all its descendants
# (see services.hierarchy.expand_district_scope), demonstrating the
# hierarchical inheritance rule from arch-02.
DEV_PERSONAS: list[DevPersona] = [
    DevPersona(id="anna", label="Anna Berg — LV Berlin", anchor_district_name="LV Berlin"),
    DevPersona(
        id="jonas",
        label="Jonas Krüger — BV Friedrichshain-Kreuzberg",
        anchor_district_name="BV Friedrichshain-Kreuzberg",
    ),
    DevPersona(id="mira", label="Mira Noll — OV Kreuzberg", anchor_district_name="OV Kreuzberg"),
    DevPersona(id="peter", label="Peter Sailer — BV Mitte", anchor_district_name="BV Mitte"),
]


def _serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt="dpp-dev-impersonation")


def encode_identity_cookie(secret: str, user_id: str, roles: tuple[str, ...], district_scopes: set[str]) -> str:
    payload = {"user_id": user_id, "roles": list(roles), "district_scopes": sorted(district_scopes)}
    return _serializer(secret).dumps(payload)


def _decode_identity_cookie(secret: str, value: str) -> dict | None:
    try:
        return _serializer(secret).loads(value)
    except BadSignature:
        return None


class DevImpersonationMiddleware:
    """Pure ASGI middleware: reads the signed impersonation cookie and, if
    present, injects the forward-auth headers before the request reaches any
    route. Never overrides real headers if they're already set.
    """

    def __init__(self, app: ASGIApp, secret: str) -> None:
        self.app = app
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        if headers.get(USER_ID_HEADER):
            # Real forward-auth headers already present; never override them.
            await self.app(scope, receive, send)
            return

        cookie_header = headers.get("cookie")
        identity_payload = None
        if cookie_header:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            morsel = cookie.get(IMPERSONATION_COOKIE)
            if morsel:
                identity_payload = _decode_identity_cookie(self.secret, morsel.value)

        if identity_payload:
            headers[USER_ID_HEADER] = identity_payload["user_id"]
            headers[USER_ROLES_HEADER] = ",".join(identity_payload["roles"])
            headers[DISTRICT_SCOPES_HEADER] = ",".join(identity_payload["district_scopes"])

        await self.app(scope, receive, send)
