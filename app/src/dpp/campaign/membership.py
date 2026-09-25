import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dpp.campaign.hierarchy import expand_district_scope
from dpp.campaign.models import Campaign, District, Initiative, InitiativeCampaign


class InitiativeMembershipError(Exception):
    """Raised when a campaign can't join an initiative. See canv-01: v1
    restricts members to the initiative's anchor district and descendants.
    """


def create_initiative(district_id: uuid.UUID, name: str, description: str | None) -> Initiative:
    return Initiative(district_id=district_id, name=name, description=description)


def update_initiative(initiative: Initiative, name: str, description: str | None) -> None:
    initiative.name = name
    initiative.description = description


async def add_campaign(session: AsyncSession, initiative: Initiative, campaign: Campaign) -> InitiativeCampaign:
    scope = await expand_district_scope(session, initiative.district_id)
    if str(campaign.district_id) not in scope:
        raise InitiativeMembershipError(
            "Campaign must belong to the initiative's anchor district or one of its descendants (see canv-01)."
        )
    link = InitiativeCampaign(initiative_id=initiative.id, campaign_id=campaign.id)
    session.add(link)
    return link


async def get_member_campaigns(session: AsyncSession, initiative_id: uuid.UUID) -> list[Campaign]:
    result = await session.execute(
        select(Campaign)
        .options(selectinload(Campaign.district))
        .join(InitiativeCampaign, InitiativeCampaign.campaign_id == Campaign.id)
        .where(InitiativeCampaign.initiative_id == initiative_id)
    )
    return list(result.scalars().all())


async def get_member_districts_by_initiative(
    session: AsyncSession, initiative_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[District]]:
    if not initiative_ids:
        return {}

    result = await session.execute(
        select(InitiativeCampaign.initiative_id, District)
        .join(Campaign, Campaign.id == InitiativeCampaign.campaign_id)
        .join(District, District.id == Campaign.district_id)
        .where(InitiativeCampaign.initiative_id.in_(initiative_ids))
        .distinct()
        .order_by(District.name)
    )
    grouped: dict[uuid.UUID, list[District]] = {initiative_id: [] for initiative_id in initiative_ids}
    for initiative_id, district in result.all():
        grouped[initiative_id].append(district)
    return grouped


async def delete_initiative(session: AsyncSession, initiative: Initiative) -> None:
    """Delete the initiative and its campaign links, never the campaigns."""
    await session.delete(initiative)


async def initiatives_for_campaign(session: AsyncSession, campaign_id: uuid.UUID) -> list[Initiative]:
    result = await session.execute(
        select(Initiative)
        .join(InitiativeCampaign, InitiativeCampaign.initiative_id == Initiative.id)
        .where(InitiativeCampaign.campaign_id == campaign_id)
    )
    return list(result.scalars().all())
