import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dpp.campaign.models import Campaign, Initiative, InitiativeCampaign


class InitiativeMembershipError(Exception):
    """Raised when a campaign can't join an initiative. See canv-01: v1
    requires an initiative's members to share its district.
    """


def create_initiative(district_id: uuid.UUID, name: str, description: str | None) -> Initiative:
    return Initiative(district_id=district_id, name=name, description=description)


async def add_campaign(session: AsyncSession, initiative: Initiative, campaign: Campaign) -> InitiativeCampaign:
    if campaign.district_id != initiative.district_id:
        raise InitiativeMembershipError(
            "Campaign must belong to the same district as the initiative (v1 constraint, see canv-01)."
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


async def initiatives_for_campaign(session: AsyncSession, campaign_id: uuid.UUID) -> list[Initiative]:
    result = await session.execute(
        select(Initiative)
        .join(InitiativeCampaign, InitiativeCampaign.initiative_id == Initiative.id)
        .where(InitiativeCampaign.campaign_id == campaign_id)
    )
    return list(result.scalars().all())
