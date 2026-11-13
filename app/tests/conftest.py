import os
import uuid

# Must happen before any `dpp.*` import: dpp.db builds its engine at import
# time from settings read from the environment, and dpp.gliederungen loads
# the registry from DPP_GLIEDERUNGEN_FILE once per process.
import pathlib

os.environ["DATABASE_URL"] = "postgresql+asyncpg://dpp:dpp@localhost:5432/dpp_test"
os.environ["APP_ENV"] = "test"
os.environ.setdefault("SESSION_SECRET", "test-secret")
# Never reach the real TypeSafe API from tests, even if a developer .env sets a key.
os.environ["TYPESAFE_API_KEY"] = ""
# Tests use the same bundled Gliederung config as local development.
os.environ.setdefault(
    "DPP_GLIEDERUNGEN_FILE",
    str(pathlib.Path(__file__).resolve().parent.parent / "config" / "gliederungen.yaml"),
)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from dpp.campaign.models import (  # noqa: F401
    Campaign,
    Initiative,
    InitiativeCampaign,
    Retrospective,
)
from dpp.crowd.models import Question, Questionnaire, Response  # noqa: F401
from dpp.db import Base, async_session_factory, engine
from dpp.main import app

ADMIN_DATABASE_URL = "postgresql+asyncpg://dpp:dpp@localhost:5432/dpp"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_database():
    admin_engine = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'dpp_test'"))
        if exists.scalar() is None:
            await conn.execute(text("CREATE DATABASE dpp_test"))
    await admin_engine.dispose()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    yield
    async with engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def auth_headers(
    user_id: str,
    groups: tuple[str, ...],
    display_name: str | None = None,
    email: str | None = None,
) -> dict[str, str]:
    """Build forward-auth headers directly (arch-01), bypassing dev impersonation.

    groups mirrors the X-Auth-Request-Groups header oauth2-proxy relays from
    the Auth0 groups claim (Gliederung slugs or "all"); dpp.auth.headers
    expands it to district scopes per the arch-02 inheritance rule.
    display_name/email mirror the X-Auth-Request-* headers oauth2-proxy relays
    in production (the display-name fallback chain source).
    """
    headers = {
        "X-User-Id": user_id,
        "X-Auth-Request-Groups": ",".join(groups),
    }
    if display_name is not None:
        headers["X-Auth-Request-Preferred-Username"] = display_name
    if email is not None:
        headers["X-Auth-Request-Email"] = email
    return headers
