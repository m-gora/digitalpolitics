import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dpp.campaign import events
from dpp.campaign.models import (
    ALLOWED_TRANSITIONS,
    CLOSED_STATUSES,
    Campaign,
    CampaignStatus,
    Retrospective,
)

NARRATIVE_FIELDS = ("thema", "ziel", "storytelling")


class GatingError(Exception):
    """Raised when a field update violates the Zieldefinition ->
    Zielgruppen & Kanäle -> Material, Organisation & Storytelling gate
    or when the campaign is not in an editable status. See canv-02/canv-05.
    """


class InvalidTransitionError(Exception):
    """Raised when a lifecycle status transition is not allowed. See canv-05."""


def create_campaign(district_id: uuid.UUID) -> Campaign:
    return Campaign(district_id=district_id, status=CampaignStatus.DRAFT)


def apply_field_updates(campaign: Campaign, updates: dict[str, str]) -> set[str]:
    """Apply field updates honoring the Zieldefinition -> Zielgruppen & Kanäle
    -> Material, Organisation & Storytelling gate.

    Only Draft campaigns are editable (canv-05). Returns the set of field
    names that were actually changed (used to decide whether to recompute
    the narrative embedding / notify SSE subscribers).
    """
    if campaign.status != CampaignStatus.DRAFT:
        raise GatingError("Campaign is not editable in its current status.")

    goal_updates = {key: value for key, value in updates.items() if key in Campaign.GOAL_FIELDS}
    audience_updates = {key: value for key, value in updates.items() if key in Campaign.AUDIENCE_FIELDS}
    execution_updates = {key: value for key, value in updates.items() if key in Campaign.EXECUTION_FIELDS}

    unknown = set(updates) - set(Campaign.GOAL_FIELDS) - set(Campaign.AUDIENCE_FIELDS) - set(Campaign.EXECUTION_FIELDS)
    if unknown:
        raise GatingError(f"Unknown canvas field(s): {', '.join(sorted(unknown))}")

    changed: set[str] = set()

    for field, value in goal_updates.items():
        if getattr(campaign, field) != value:
            setattr(campaign, field, value)
            changed.add(field)

    if audience_updates and not campaign.goal_complete:
        raise GatingError("Complete the Zieldefinition before editing Zielgruppen & Kanäle.")
    for field, value in audience_updates.items():
        if getattr(campaign, field) != value:
            setattr(campaign, field, value)
            changed.add(field)

    if execution_updates and not campaign.execution_unlocked:
        raise GatingError("Complete Zieldefinition and Zielgruppen & Kanäle before editing Material, Organisation & Storytelling.")
    for field, value in execution_updates.items():
        if getattr(campaign, field) != value:
            setattr(campaign, field, value)
            changed.add(field)

    return changed


async def transition_status(
    session: AsyncSession, campaign: Campaign, to_status: CampaignStatus
) -> Retrospective | None:
    """Move a campaign to a new lifecycle status (canv-05).

    Returns the (possibly newly created) Retrospective if the campaign just
    closed (Finished/Aborted), otherwise None.
    """
    allowed = ALLOWED_TRANSITIONS.get(campaign.status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(f"Cannot transition from {campaign.status.value} to {to_status.value}.")

    campaign.status = to_status

    retro: Retrospective | None = None
    if to_status in CLOSED_STATUSES and to_status != CampaignStatus.ARCHIVED:
        # Auto-create an empty retrospective on Finished/Aborted (canv-04).
        if campaign.retrospective is None:
            retro = Retrospective(campaign_id=campaign.id)
            session.add(retro)
            campaign.retrospective = retro
        else:
            retro = campaign.retrospective

    await events.publish_status_changed(str(campaign.id), to_status.value)
    return retro


def fork_campaign(source: Campaign, target_district_id: uuid.UUID) -> Campaign:
    """Copy canvas field answers only into a new Draft campaign (canv-03).

    Hierarchy placement (the caller-supplied target_district_id), initiative
    membership, and any collected data are deliberately NOT copied.
    """
    fields = {f: getattr(source, f) for f in Campaign.GOAL_FIELDS + Campaign.AUDIENCE_FIELDS + Campaign.EXECUTION_FIELDS}
    return Campaign(
        district_id=target_district_id,
        status=CampaignStatus.DRAFT,
        forked_from_id=source.id,
        **fields,
    )
