"""Dev impersonation must stay a convenience, never a 500 generator."""

import asyncio

from dpp.auth.dev_impersonation import (
    IMPERSONATION_COOKIE,
    DevImpersonationMiddleware,
    _serializer,
)
from dpp.auth.headers import USER_GROUPS_HEADER, USER_ID_HEADER

SECRET = "test-secret"


def _run_with_cookie(value: str) -> dict[str, str]:
    captured: dict[str, str] = {}

    async def app(scope, receive, send):
        captured.update({key.decode(): val.decode() for key, val in scope["headers"]})

    middleware = DevImpersonationMiddleware(app, secret=SECRET)
    scope = {
        "type": "http",
        "headers": [(b"cookie", f"{IMPERSONATION_COOKIE}={value}".encode())],
    }
    asyncio.run(middleware(scope, None, None))
    return captured


def test_cookie_injects_identity_headers():
    value = _serializer(SECRET).dumps(
        {"user_id": "anna", "groups": ["lv-berlin"], "name": "Anna"}
    )
    headers = _run_with_cookie(value)

    assert headers[USER_ID_HEADER.lower()] == "anna"
    assert headers[USER_GROUPS_HEADER.lower()] == "lv-berlin"
    assert headers["x-auth-request-preferred-username"] == "Anna"


def test_cookie_from_older_payload_shape_is_ignored():
    """A still-valid signature with no groups must not crash the request."""
    headers = _run_with_cookie(_serializer(SECRET).dumps({"user_id": "anna"}))

    assert USER_ID_HEADER.lower() not in headers
    assert USER_GROUPS_HEADER.lower() not in headers
