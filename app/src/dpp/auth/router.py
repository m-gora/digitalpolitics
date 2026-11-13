"""Dev-only impersonation endpoints. Only mounted when APP_ENV=development
(see dpp.main). See dpp.auth.dev_impersonation for the header-injection side.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from dpp.auth.dev_impersonation import (
    DEV_PERSONAS,
    IMPERSONATION_COOKIE,
    encode_identity_cookie,
)
from dpp.config import get_settings

router = APIRouter(prefix="/_dev", tags=["dev"])


@router.post("/impersonate")
async def impersonate(
    request: Request,
    persona_id: str = Form(...),
):
    persona = next((p for p in DEV_PERSONAS if p.id == persona_id), None)
    if persona is None:
        return RedirectResponse(url="/", status_code=303)

    settings = get_settings()
    cookie_value = encode_identity_cookie(
        secret=settings.session_secret,
        user_id=persona.id,
        groups=(persona.group,),
        name=persona.name,
        email=persona.email,
    )

    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie(IMPERSONATION_COOKIE, cookie_value, httponly=True, samesite="lax")
    return response


@router.post("/logout")
async def logout(request: Request):
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    response.delete_cookie(IMPERSONATION_COOKIE)
    return response
