"""Dev-only design system styleguide.

Renders the token/component contract in one page so it can be reviewed
visually instead of by reading class strings. Mounted only when
APP_ENV=development (see dpp.main); every other environment gets a 404, so the
route can never expose internal UI scaffolding in a deployment.
"""

from fastapi import APIRouter, HTTPException, Request

from dpp.auth.headers import parse_identity
from dpp.config import get_settings
from dpp.templating import templates

router = APIRouter(tags=["design"])


@router.get("/_design", include_in_schema=False)
async def design_styleguide(request: Request):
    if not get_settings().is_development:
        raise HTTPException(status_code=404)

    # Identity is optional here: the styleguide must render before a dev
    # persona has been picked, otherwise there is a login loop just to look
    # at swatches.
    return templates.TemplateResponse(
        request,
        "design/index.html",
        {"identity": parse_identity(request)},
    )
