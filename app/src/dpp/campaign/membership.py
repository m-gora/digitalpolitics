import uuid

import dpp.gliederungen as gliederungen
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dpp.campaign.models import Campaign, Initiative, InitiativeCampaign


class InitiativeMembershipError(Exception):
    """Raised when a campaign can't join an initiative. See canv-01: v1
    restricts members to the initiative's anchor district and descendants.
    """


def create_initiative(district_slug: str, name: str, description: str | None) -> Initiative:
    return Initiative(district_slug=district_slug, name=name, description=description)


def update_initiative(initiative: Initiative, name: str, description: str | None) -> None:
    initiative.name = name
    initiative.description = description


async def add_campaign(session: AsyncSession, initiative: Initiative, campaign: Campaign) -> InitiativeCampaign:
    scope = gliederungen.get_registry().expand(initiative.district_slug)
    if campaign.district_slug not in scope:
        raise InitiativeMembershipError(
            "Campaign must belong to the initiative's anchor district or one of its descendants (see canv-01)."
        )
    link = InitiativeCampaign(initiative_id=initiative.id, campaign_id=campaign.id)
    session.add(link)
    return link


async def get_member_campaigns(session: AsyncSession, initiative_id: uuid.UUID) -> list[Campaign]:
    result = await session.execute(
        select(Campaign)
        .join(InitiativeCampaign, InitiativeCampaign.campaign_id == Campaign.id)
        .where(InitiativeCampaign.initiative_id == initiative_id)
    )
    return list(result.scalars().all())


def get_member_district_names_by_initiative(
    initiatives: list[Initiative], campaigns_by_initiative: dict[uuid.UUID, list[Campaign]]
) -> dict[uuid.UUID, list[str]]:
    """Initiative id -> sorted display names of the districts its member
    campaigns belong to, resolved from the Gliederung config registry
    (no DB districts)."""
    registry = gliederungen.get_registry()
    grouped: dict[uuid.UUID, list[str]] = {}
    for initiative in initiatives:
        names = {
            registry.name(campaign.district_slug)
            for campaign in campaigns_by_initiative.get(initiative.id, [])
            if registry.exists(campaign.district_slug)
        }
        grouped[initiative.id] = sorted(names)
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
