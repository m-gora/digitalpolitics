import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dpp.campaign.models import District


async def expand_district_scope(session: AsyncSession, root_id: uuid.UUID) -> set[str]:
    """Return {root_id} union all descendant district IDs, as strings.

    This mirrors the inheritance rule from arch-02 ("access to a district
    implies access to all districts beneath it"). Per adr-03, a real
    forward-auth proxy is responsible for this expansion; this helper exists
    so the dev impersonation flow (dpp.auth.dev_impersonation) can produce the
    same pre-expanded X-District-Scopes value locally.
    """
    scopes: set[str] = {str(root_id)}
    frontier = [root_id]
    while frontier:
        result = await session.execute(select(District.id).where(District.parent_id.in_(frontier)))
        children = list(result.scalars())
        if not children:
            break
        scopes.update(str(c) for c in children)
        frontier = children
    return scopes


async def get_tree(session: AsyncSession) -> list[District]:
    """Return all districts (flat); callers build the tree via parent_id."""
    result = await session.execute(select(District).order_by(District.name))
    return list(result.scalars().all())
