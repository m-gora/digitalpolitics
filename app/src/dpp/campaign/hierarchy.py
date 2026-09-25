import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dpp.campaign.models import District


class DistrictNotFoundError(Exception):
    """The requested parent or district doesn't exist."""


class DistrictHasChildrenError(Exception):
    """Only leaf districts can be deleted in v1."""


class DistrictInUseError(Exception):
    """A district referenced by campaigns or initiatives cannot be deleted."""


async def create_district(session: AsyncSession, name: str, parent_id: uuid.UUID | None) -> District:
    parent = None
    if parent_id is not None:
        parent = await session.get(District, parent_id)
        if parent is None:
            raise DistrictNotFoundError("Parent district not found.")

    district = District(name=name, parent=parent)
    session.add(district)
    return district


async def rename_district(session: AsyncSession, district: District, name: str) -> None:
    district.name = name
    await session.flush()


async def delete_district(session: AsyncSession, district: District) -> None:
    child_id = await session.scalar(select(District.id).where(District.parent_id == district.id).limit(1))
    if child_id is not None:
        raise DistrictHasChildrenError("Delete child districts first; only leaf districts can be deleted.")

    await session.delete(district)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DistrictInUseError("This district still has campaigns or initiatives and cannot be deleted.") from exc


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
