import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse
from starlette import status

from dpp.auth.dependencies import ensure_write_access, get_identity
from dpp.auth.headers import Identity
from dpp.campaign import coherence, events, hierarchy, lifecycle, membership
from dpp.campaign.lifecycle import NARRATIVE_FIELDS, GatingError, InvalidTransitionError
from dpp.campaign.membership import InitiativeMembershipError
from dpp.campaign.models import (
    Campaign,
    CampaignStatus,
    District,
    Initiative,
    InitiativeCampaign,
)
from dpp.db import async_session_factory, get_session
from dpp.templating import templates

# --- Districts ---------------------------------------------------------

districts_router = APIRouter(prefix="/districts", tags=["districts"])


def _build_forest(districts: list) -> list[dict]:
    by_id = {d.id: {"district": d, "children": []} for d in districts}
    roots = []
    for d in districts:
        node = by_id[d.id]
        if d.parent_id and d.parent_id in by_id:
            by_id[d.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@districts_router.get("")
async def list_districts(
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    districts = await hierarchy.get_tree(session)
    forest = _build_forest(districts)
    return templates.TemplateResponse(
        request,
        "districts/list.html",
        {"forest": forest, "identity": identity},
    )


# --- Campaigns -----------------------------------------------------------

campaigns_router = APIRouter(prefix="/campaigns", tags=["campaigns"])

WIZARD_STEPS = ("zieldefinition", "zielgruppen-kanaele", "material-organisation-storytelling")
WIZARD_FIELDS = {
    "zieldefinition": (
        ("thema", "Thema", "Worum geht es?"),
        ("ziel", "Ziel", "Was ist das Ziel (politisch und kommunikativ)?"),
    ),
    "zielgruppen-kanaele": (
        ("zielgruppen", "Zielgruppen", "Gibt es spezielle Zielgruppen?"),
        ("kanaele", "Kanäle", "Welche Zulieferer brauchen wir? Wo erreichen wir die Zielgruppe?"),
        (
            "momentum",
            "Momentum",
            "Welche Multiplikatoren haben wir in unserem Umfeld? Welche Stakeholder und Partner können wir aktivieren?",
        ),
        ("motiv", "Motiv", "Warum sollte jemand mitmachen?"),
    ),
    "material-organisation-storytelling": (
        ("service", "Service", "Was sollte man den Aktivisten zur Verfügung stellen?"),
        (
            "data_harvest",
            "Data Harvest",
            (
                "Welche Daten unserer Zielgruppe wären besonders nützlich für eine nutzenstiftende Kommunikation? "
                "Was passiert im Anschluss mit diesen Daten?"
            ),
        ),
        ("tools", "Tools", "Welche Tools könnten nützlich sein? (Apps, Petitionstools, etc.)"),
        (
            "phasen_flow",
            "Phasen & Flow",
            (
                "Wie startet die Aktion um erfolgreich Aufmerksamkeit zu erzeugen? Wie halten wir die Spannung? "
                "Wann gibt es Anlässe die wir nutzen können? Wie endet die Aktion?"
            ),
        ),
        ("storytelling", "Storytelling", "Gibt es eine spannende Perspektive, besondere Personengruppen, etc?"),
    ),
}


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


async def _get_campaign_or_404(session: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
    result = await session.execute(
        select(Campaign)
        .options(selectinload(Campaign.district), selectinload(Campaign.retrospective))
        .where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@campaigns_router.get("")
async def list_campaigns(
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    result = await session.execute(
        select(Campaign).options(selectinload(Campaign.district)).order_by(Campaign.created_at.desc())
    )
    campaigns = list(result.scalars().all())
    return templates.TemplateResponse(
        request,
        "campaigns/list.html",
        {"campaigns": campaigns, "identity": identity},
    )


@campaigns_router.get("/new")
async def new_campaign(
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    result = await session.execute(select(District).order_by(District.name))
    districts = list(result.scalars().all())
    return templates.TemplateResponse(
        request,
        "campaigns/new.html",
        {"districts": districts, "identity": identity},
    )


@campaigns_router.post("/new")
async def create_campaign_from_wizard(
    district_id: uuid.UUID = Form(...),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    ensure_write_access(identity, district_id)
    campaign = lifecycle.create_campaign(district_id)
    session.add(campaign)
    await session.commit()
    return _redirect(f"/campaigns/{campaign.id}/wizard/zieldefinition")


@campaigns_router.post("")
async def create_campaign(
    district_id: uuid.UUID = Form(...),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    ensure_write_access(identity, district_id)
    campaign = lifecycle.create_campaign(district_id)
    session.add(campaign)
    await session.commit()
    return _redirect(f"/campaigns/{campaign.id}")


@campaigns_router.get("/{campaign_id}")
async def campaign_detail(
    campaign_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    can_write = identity.has_write_access(campaign.district_id)
    initiatives = await membership.initiatives_for_campaign(session, campaign.id)
    districts_result = await session.execute(select(District).order_by(District.name))
    districts = list(districts_result.scalars().all())
    allowed_transitions = sorted(
        (s.value for s in lifecycle.ALLOWED_TRANSITIONS.get(campaign.status, set())),
    )
    wizard_step = (
        "zieldefinition"
        if not campaign.goal_complete
        else "zielgruppen-kanaele"
        if not campaign.audience_complete
        else "material-organisation-storytelling"
    )
    return templates.TemplateResponse(
        request,
        "campaigns/detail.html",
        {
            "campaign": campaign,
            "can_write": can_write,
            "identity": identity,
            "initiatives": initiatives,
            "allowed_transitions": allowed_transitions,
            "districts": districts,
            "CampaignStatus": CampaignStatus,
            "wizard_step": wizard_step,
        },
    )


async def _render_wizard(
    request: Request,
    session: AsyncSession,
    campaign: Campaign,
    identity: Identity,
    step: str,
    error: str | None = None,
):
    if step not in WIZARD_STEPS:
        raise HTTPException(status_code=404, detail="Unknown campaign wizard step")
    if campaign.status != CampaignStatus.DRAFT or not identity.has_write_access(campaign.district_id):
        return _redirect(f"/campaigns/{campaign.id}")

    if step == "zielgruppen-kanaele" and not campaign.audience_unlocked:
        return _redirect(f"/campaigns/{campaign.id}/wizard/zieldefinition")
    if step == "material-organisation-storytelling" and not campaign.execution_unlocked:
        next_step = "zielgruppen-kanaele" if campaign.audience_unlocked else "zieldefinition"
        return _redirect(f"/campaigns/{campaign.id}/wizard/{next_step}")

    result = await session.execute(select(District).order_by(District.name))
    districts = list(result.scalars().all())
    return templates.TemplateResponse(
        request,
        "campaigns/wizard.html",
        {
            "campaign": campaign,
            "identity": identity,
            "step": step,
            "steps": WIZARD_STEPS,
            "fields": WIZARD_FIELDS[step],
            "field_values": {name: getattr(campaign, name) or "" for name, _, _ in WIZARD_FIELDS[step]},
            "districts": districts,
            "error": error,
        },
    )


@campaigns_router.get("/{campaign_id}/wizard/{step}")
async def campaign_wizard_step(
    campaign_id: uuid.UUID,
    step: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    return await _render_wizard(request, session, campaign, identity, step)


@campaigns_router.post("/{campaign_id}/wizard/{step}")
async def save_campaign_wizard_step(
    campaign_id: uuid.UUID,
    step: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    ensure_write_access(identity, campaign.district_id)
    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only Draft campaigns can be edited.")
    if step not in WIZARD_STEPS:
        raise HTTPException(status_code=404, detail="Unknown campaign wizard step")
    if step == "zielgruppen-kanaele" and not campaign.audience_unlocked:
        return _redirect(f"/campaigns/{campaign.id}/wizard/zieldefinition")
    if step == "material-organisation-storytelling" and not campaign.execution_unlocked:
        next_step = "zielgruppen-kanaele" if campaign.audience_unlocked else "zieldefinition"
        return _redirect(f"/campaigns/{campaign.id}/wizard/{next_step}")

    form = await request.form()
    updates = {name: str(form.get(name, "")) for name, _, _ in WIZARD_FIELDS[step]}
    try:
        changed = lifecycle.apply_field_updates(campaign, updates)
    except GatingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    for field in changed:
        await events.publish_field_updated(str(campaign.id), field)
    if changed & set(NARRATIVE_FIELDS):
        background_tasks.add_task(_recompute_embedding_and_coherence, campaign.id)

    action = str(form.get("action", "next"))
    if action == "back":
        previous = {
            "zielgruppen-kanaele": "zieldefinition",
            "material-organisation-storytelling": "zielgruppen-kanaele",
        }.get(step)
        return _redirect(f"/campaigns/{campaign.id}/wizard/{previous}" if previous else "/campaigns")
    if action == "finish" and step == "material-organisation-storytelling":
        return _redirect(f"/campaigns/{campaign.id}")

    complete = campaign.goal_complete if step == "zieldefinition" else campaign.audience_complete
    if action == "next" and not complete:
        message = "Bitte fülle alle Felder dieses Schritts aus, bevor du fortfährst."
        return await _render_wizard(request, session, campaign, identity, step, error=message)

    next_step = {
        "zieldefinition": "zielgruppen-kanaele",
        "zielgruppen-kanaele": "material-organisation-storytelling",
    }.get(step)
    if next_step:
        return _redirect(f"/campaigns/{campaign.id}/wizard/{next_step}")
    return _redirect(f"/campaigns/{campaign.id}")


async def _recompute_embedding_and_coherence(campaign_id: uuid.UUID) -> None:
    """Background task: recompute a campaign's narrative embedding, then the
    coherence score of every initiative it belongs to (canv-01).
    """
    async with async_session_factory() as session:
        campaign = await _get_campaign_or_404(session, campaign_id)
        changed = await coherence.update_campaign_embedding(campaign)
        if changed:
            await session.commit()
        initiatives = await membership.initiatives_for_campaign(session, campaign_id)
        for initiative in initiatives:
            await coherence.recompute_coherence(session, initiative)
        await session.commit()


@campaigns_router.post("/{campaign_id}/fields")
async def update_fields(
    campaign_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    ensure_write_access(identity, campaign.district_id)

    form = await request.form()
    updates = {k: v for k, v in form.items() if isinstance(v, str) and v.strip() != ""}

    try:
        changed = lifecycle.apply_field_updates(campaign, updates)
    except GatingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()

    for field in changed:
        await events.publish_field_updated(str(campaign.id), field)

    if changed & set(NARRATIVE_FIELDS):
        background_tasks.add_task(_recompute_embedding_and_coherence, campaign.id)

    return _redirect(f"/campaigns/{campaign.id}")


@campaigns_router.post("/{campaign_id}/transition")
async def transition(
    campaign_id: uuid.UUID,
    to_status: str = Form(...),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    ensure_write_access(identity, campaign.district_id)

    try:
        target = CampaignStatus(to_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown status") from exc

    try:
        await lifecycle.transition_status(session, campaign, target)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    return _redirect(f"/campaigns/{campaign.id}")


@campaigns_router.post("/{campaign_id}/fork")
async def fork(
    campaign_id: uuid.UUID,
    target_district_id: uuid.UUID = Form(...),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    source = await _get_campaign_or_404(session, campaign_id)  # read is global, per arch-02
    ensure_write_access(identity, target_district_id)

    forked = lifecycle.fork_campaign(source, target_district_id)
    session.add(forked)
    await session.commit()
    return _redirect(f"/campaigns/{forked.id}")


@campaigns_router.get("/{campaign_id}/retrospective")
async def retrospective_view(
    campaign_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    can_write = identity.has_write_access(campaign.district_id) and campaign.status != CampaignStatus.ARCHIVED
    return templates.TemplateResponse(
        request,
        "campaigns/retrospective.html",
        {"campaign": campaign, "can_write": can_write, "identity": identity},
    )


@campaigns_router.post("/{campaign_id}/retrospective")
async def retrospective_update(
    campaign_id: uuid.UUID,
    zielerreichung: str = Form(""),
    was_lief_gut: str = Form(""),
    was_lief_schlecht: str = Form(""),
    handlungsempfehlungen: str = Form(""),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    campaign = await _get_campaign_or_404(session, campaign_id)
    ensure_write_access(identity, campaign.district_id)

    if campaign.status == CampaignStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="Archived campaigns are read-only.")
    if campaign.retrospective is None:
        raise HTTPException(
            status_code=400, detail="Retrospective is only available once a campaign is Finished/Aborted."
        )

    campaign.retrospective.zielerreichung = zielerreichung
    campaign.retrospective.was_lief_gut = was_lief_gut
    campaign.retrospective.was_lief_schlecht = was_lief_schlecht
    campaign.retrospective.handlungsempfehlungen = handlungsempfehlungen

    await session.commit()
    return _redirect(f"/campaigns/{campaign.id}/retrospective")


# --- Initiatives -----------------------------------------------------------

initiatives_router = APIRouter(prefix="/initiatives", tags=["initiatives"])


async def _get_initiative_or_404(session: AsyncSession, initiative_id: uuid.UUID) -> Initiative:
    result = await session.execute(
        select(Initiative).options(selectinload(Initiative.district)).where(Initiative.id == initiative_id)
    )
    initiative = result.scalar_one_or_none()
    if initiative is None:
        raise HTTPException(status_code=404, detail="Initiative not found")
    return initiative


@initiatives_router.get("")
async def list_initiatives(
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    result = await session.execute(select(Initiative).options(selectinload(Initiative.district)))
    initiatives = list(result.scalars().all())
    districts_result = await session.execute(select(District).order_by(District.name))
    districts = list(districts_result.scalars().all())
    return templates.TemplateResponse(
        request,
        "initiatives/list.html",
        {"initiatives": initiatives, "districts": districts, "identity": identity},
    )


@initiatives_router.post("")
async def create_initiative(
    district_id: uuid.UUID = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    ensure_write_access(identity, district_id)
    initiative = membership.create_initiative(district_id, name, description or None)
    session.add(initiative)
    await session.commit()
    return _redirect(f"/initiatives/{initiative.id}")


@initiatives_router.get("/{initiative_id}")
async def initiative_detail(
    initiative_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    initiative = await _get_initiative_or_404(session, initiative_id)
    members = await membership.get_member_campaigns(session, initiative.id)

    # Campaigns in the same district not yet part of this initiative (v1: same-district only, canv-01).
    member_ids = {m.id for m in members}
    candidates_result = await session.execute(select(Campaign).where(Campaign.district_id == initiative.district_id))
    candidates = [c for c in candidates_result.scalars().all() if c.id not in member_ids]

    can_write = identity.has_write_access(initiative.district_id)
    return templates.TemplateResponse(
        request,
        "initiatives/detail.html",
        {
            "initiative": initiative,
            "members": members,
            "candidates": candidates,
            "can_write": can_write,
            "identity": identity,
        },
    )


@initiatives_router.post("/{initiative_id}/members")
async def add_member(
    initiative_id: uuid.UUID,
    campaign_id: uuid.UUID = Form(...),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    initiative = await _get_initiative_or_404(session, initiative_id)
    ensure_write_access(identity, initiative.district_id)

    campaign_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        await membership.add_campaign(session, initiative, campaign)
    except InitiativeMembershipError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.flush()
    await coherence.recompute_coherence(session, initiative)
    await session.commit()
    return _redirect(f"/initiatives/{initiative.id}")


@initiatives_router.post("/{initiative_id}/members/{campaign_id}/remove")
async def remove_member(
    initiative_id: uuid.UUID,
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    initiative = await _get_initiative_or_404(session, initiative_id)
    ensure_write_access(identity, initiative.district_id)

    result = await session.execute(
        select(InitiativeCampaign).where(
            InitiativeCampaign.initiative_id == initiative_id,
            InitiativeCampaign.campaign_id == campaign_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is not None:
        await session.delete(link)
        await session.flush()
        await coherence.recompute_coherence(session, initiative)
        await session.commit()

    return _redirect(f"/initiatives/{initiative.id}")


# --- Events (SSE) ------------------------------------------------------

events_router = APIRouter(prefix="/events", tags=["events"])


@events_router.get("/canvas")
async def canvas_events(identity: Identity = Depends(get_identity)):
    """Single SSE channel for the canvas module (arch-03). Read access is
    global (arch-02), so any authenticated user may subscribe.
    """
    return EventSourceResponse(events.canvas_channel.stream())
