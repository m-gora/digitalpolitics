import os
import uuid

# Must happen before any `dpp.*` import: dpp.db builds its engine at import
# time from settings read from the environment.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://dpp:dpp@localhost:5432/dpp_test"
os.environ["APP_ENV"] = "test"
os.environ.setdefault("SESSION_SECRET", "test-secret")
# Never reach the real TypeSafe API from tests, even if a developer .env sets a key.
os.environ["TYPESAFE_API_KEY"] = ""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from dpp.campaign.models import (  # noqa: F401
    Campaign,
    District,
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


def auth_headers(user_id: str, district_scopes: set[str], roles: tuple[str, ...] = ("member",)) -> dict[str, str]:
    """Build forward-auth headers directly (arch-01), bypassing dev impersonation."""
    return {
        "X-User-Id": user_id,
        "X-User-Roles": ",".join(roles),
        "X-District-Scopes": ",".join(district_scopes),
    }


async def make_district(session, name: str, parent=None) -> District:
    d = District(id=uuid.uuid4(), name=name, parent=parent)
    session.add(d)
    await session.commit()
    await session.refresh(d)
    return d
