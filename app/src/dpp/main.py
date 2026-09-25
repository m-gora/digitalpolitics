from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from dpp.auth.dependencies import get_identity
from dpp.auth.headers import Identity
from dpp.campaign.router import (
    campaigns_router,
    districts_router,
    events_router,
    initiatives_router,
)
from dpp.config import get_settings
from dpp.templating import templates

STATIC_DIR = Path(__file__).parent / "static"

settings = get_settings()

app = FastAPI(title="FDP Digital Politics Platform")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(districts_router)
app.include_router(campaigns_router)
app.include_router(initiatives_router)
app.include_router(events_router)

templates.env.globals["is_development"] = settings.is_development
templates.env.globals["dev_personas"] = []

if settings.is_development:
    # Dev-only forward-auth header simulation. See dpp.auth.dev_impersonation.
    # This must never be wired up outside APP_ENV=development.
    from dpp.auth.dev_impersonation import DEV_PERSONAS, DevImpersonationMiddleware
    from dpp.auth.router import router as dev_router

    app.add_middleware(DevImpersonationMiddleware, secret=settings.session_secret)
    app.include_router(dev_router)
    templates.env.globals["dev_personas"] = DEV_PERSONAS


@app.exception_handler(HTTPException)
async def html_aware_http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Render a friendly page (with the dev impersonation bar, if applicable)
    for 401s reached via regular browser navigation. Everything else (SSE,
    htmx/JSON-ish requests without an HTML Accept header) keeps the default
    JSON error body FastAPI/Starlette would otherwise return.
    """
    wants_html = "text/html" in request.headers.get("accept", "")
    if exc.status_code == 401 and wants_html:
        return templates.TemplateResponse(request, "auth_required.html", {"identity": None}, status_code=401)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.get("/")
async def index(request: Request, identity: Identity = Depends(get_identity)):
    return templates.TemplateResponse(request, "landing.html", {"identity": identity})
