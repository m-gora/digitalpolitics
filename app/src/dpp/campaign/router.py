import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import exists, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload
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
from dpp.campaign.summary import update_campaign_summary
from dpp.crowd.models import Questionnaire
from dpp.crowd.models import Response as CrowdResponse
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
    district_choices = _flatten_forest(forest)
    error_messages = {
        "empty_name": "Bitte gib einen Namen für die Gliederung ein.",
        "has_children": "Untergliederungen zuerst einzeln löschen.",
        "in_use": "Diese Gliederung ist noch mit Kampagnen oder Initiativen verknüpft und kann nicht gelöscht werden.",
        "parent_not_found": "Die übergeordnete Gliederung wurde nicht gefunden.",
    }
    return templates.TemplateResponse(
        request,
        "districts/list.html",
        {
            "forest": forest,
            "district_choices": district_choices,
            "identity": identity,
            "error_message": error_messages.get(request.query_params.get("error", "")),
        },
    )


def _flatten_forest(nodes: list[dict], depth: int = 0) -> list[dict]:
    flattened = []
    for node in nodes:
        flattened.append({"district": node["district"], "depth": depth})
        flattened.extend(_flatten_forest(node["children"], depth + 1))
    return flattened


@districts_router.post("")
async def create_district(
    name: str = Form(...),
    parent_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    name = name.strip()
    if not name:
        return _redirect("/districts?error=empty_name")

    parent_uuid = None
    if parent_id:
        try:
            parent_uuid = uuid.UUID(parent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid parent district ID.") from exc
        ensure_write_access(identity, parent_uuid)

    try:
        await hierarchy.create_district(session, name, parent_uuid)
    except hierarchy.DistrictNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return _redirect("/districts")


@districts_router.post("/{district_id}/rename")
async def rename_district(
    district_id: uuid.UUID,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    district = await session.get(District, district_id)
    if district is None:
        raise HTTPException(status_code=404, detail="District not found.")
    ensure_write_access(identity, district.id)
    name = name.strip()
    if not name:
        return _redirect("/districts?error=empty_name")

    await hierarchy.rename_district(session, district, name)
    await session.commit()
    return _redirect("/districts")


@districts_router.post("/{district_id}/delete")
async def delete_district(
    district_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    district = await session.get(District, district_id)
    if district is None:
        raise HTTPException(status_code=404, detail="District not found.")
    ensure_write_access(identity, district.id)

    try:
        await hierarchy.delete_district(session, district)
    except hierarchy.DistrictHasChildrenError:
        return _redirect("/districts?error=has_children")
    except hierarchy.DistrictInUseError:
        return _redirect("/districts?error=in_use")

    await session.commit()
    return _redirect("/districts")


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
    q: str = "",
    status_filter: str = Query(default="running", alias="status"),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    search_query = q.strip()
    if status_filter != "all":
        try:
            campaign_status = CampaignStatus(status_filter)
        except ValueError as exc:
            valid_statuses = ", ".join(status.value for status in CampaignStatus)
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status. Choose one of: {valid_statuses}, all",
            ) from exc
    else:
        campaign_status = None

    query = (
        select(Campaign)
        .join(Campaign.district)
        .options(contains_eager(Campaign.district))
        .order_by(Campaign.created_at.desc())
    )
    if campaign_status is not None:
        query = query.where(Campaign.status == campaign_status)
    if search_query:
        search_config = literal_column("'german'::regconfig")
        tsquery = func.plainto_tsquery(search_config, search_query)
        district_search_vector = func.to_tsvector(search_config, District.name)
        query = query.where(
            or_(
                Campaign.search_vector.op("@@")(tsquery),
                district_search_vector.op("@@")(tsquery),
            )
        )

    result = await session.execute(query)
    campaigns = list(result.scalars().all())
    has_campaigns = bool(campaigns)
    if not has_campaigns:
        has_campaigns = bool(await session.scalar(select(exists().select_from(Campaign))))
    return templates.TemplateResponse(
        request,
        "campaigns/list.html",
        {
            "campaigns": campaigns,
            "identity": identity,
            "search_query": search_query,
            "selected_status": status_filter,
            "status_choices": list(CampaignStatus),
            "has_campaigns": has_campaigns,
        },
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
    campaign = lifecycle.create_campaign(district_id, created_by=identity.user_id)
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
    campaign = lifecycle.create_campaign(district_id, created_by=identity.user_id)
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
    crowd_questionnaires = list((await session.scalars(select(Questionnaire).where(Questionnaire.campaign_id == campaign.id).order_by(Questionnaire.created_at.desc()))).all())
    crowd_counts = {
        q.id: await session.scalar(select(func.count(CrowdResponse.id)).where(CrowdResponse.questionnaire_id == q.id))
        for q in crowd_questionnaires
    }
    can_write = identity.has_write_access(campaign.district_id)
    initiatives = await membership.initiatives_for_campaign(session, campaign.id)
    districts_result = await session.execute(select(District).order_by(District.name))
    districts = list(districts_result.scalars().all())
    allowed_transitions = sorted(
        lifecycle.ALLOWED_TRANSITIONS.get(campaign.status, set()),
        key=lambda campaign_status: campaign_status.value,
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
            "crowd_questionnaires": crowd_questionnaires,
            "crowd_counts": crowd_counts,
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
        background_tasks.add_task(_recompute_campaign_coherence, campaign.id)
    if changed and campaign.canvas_complete:
        background_tasks.add_task(_recompute_campaign_summary, campaign.id)

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


async def _recompute_campaign_coherence(campaign_id: uuid.UUID) -> None:
    """Rescore every initiative the campaign belongs to after its narrative text changed (canv-01)."""
    async with async_session_factory() as session:
        initiatives = await membership.initiatives_for_campaign(session, campaign_id)
        for initiative in initiatives:
            await coherence.recompute_and_publish(session, initiative)


async def _recompute_initiative_coherence(initiative_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        initiative = await session.get(Initiative, initiative_id)
        if initiative is not None:
            await coherence.recompute_and_publish(session, initiative)


async def _recompute_campaign_summary(campaign_id: uuid.UUID) -> None:
    """Regenerate the list-view summary after a complete canvas is edited."""
    async with async_session_factory() as session:
        campaign = await _get_campaign_or_404(session, campaign_id)
        updated = await update_campaign_summary(campaign)
        if updated:
            await session.commit()
            await events.publish_summary_updated(str(campaign.id))


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
        background_tasks.add_task(_recompute_campaign_coherence, campaign.id)
    if changed and campaign.canvas_complete:
        background_tasks.add_task(_recompute_campaign_summary, campaign.id)

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

    closed_questionnaire_ids = []
    if target in {CampaignStatus.FINISHED, CampaignStatus.ABORTED, CampaignStatus.ARCHIVED}:
        from dpp.crowd.service import close_active_questionnaires_for_campaign

        closed_questionnaire_ids = await close_active_questionnaires_for_campaign(session, campaign.id)
    await session.commit()
    if closed_questionnaire_ids:
        from dpp.crowd.events import publish_questionnaire_status

        for questionnaire_id in closed_questionnaire_ids:
            await publish_questionnaire_status(str(questionnaire_id), "closed")
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

    forked = lifecycle.fork_campaign(source, target_district_id, created_by=identity.user_id)
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
    districts_by_initiative = await membership.get_member_districts_by_initiative(
        session, [initiative.id for initiative in initiatives]
    )
    districts_result = await session.execute(select(District).order_by(District.name))
    districts = list(districts_result.scalars().all())
    return templates.TemplateResponse(
        request,
        "initiatives/list.html",
        {
            "initiatives": initiatives,
            "districts_by_initiative": districts_by_initiative,
            "districts": districts,
            "identity": identity,
        },
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


@initiatives_router.post("/{initiative_id}/edit")
async def edit_initiative(
    initiative_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    initiative = await _get_initiative_or_404(session, initiative_id)
    ensure_write_access(identity, initiative.district_id)
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Initiative name cannot be empty.")

    description = description.strip() or None
    context_changed = (initiative.name, initiative.description) != (name, description)
    membership.update_initiative(initiative, name, description)
    await session.commit()
    if context_changed:
        background_tasks.add_task(_recompute_initiative_coherence, initiative.id)
    return _redirect(f"/initiatives/{initiative.id}")


@initiatives_router.post("/{initiative_id}/delete")
async def delete_initiative(
    initiative_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    initiative = await _get_initiative_or_404(session, initiative_id)
    ensure_write_access(identity, initiative.district_id)
    await membership.delete_initiative(session, initiative)
    await session.commit()
    return _redirect("/initiatives")


@initiatives_router.get("/{initiative_id}")
async def initiative_detail(
    initiative_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    initiative = await _get_initiative_or_404(session, initiative_id)
    members = await membership.get_member_campaigns(session, initiative.id)

    # Campaigns from the anchor district and descendants can join (canv-01).
    member_ids = {m.id for m in members}
    scope = await hierarchy.expand_district_scope(session, initiative.district_id)
    scope_ids = [uuid.UUID(district_id) for district_id in scope]
    candidates_result = await session.execute(
        select(Campaign)
        .options(selectinload(Campaign.district))
        .where(Campaign.district_id.in_(scope_ids))
    )
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
    background_tasks: BackgroundTasks,
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

    await session.commit()
    background_tasks.add_task(_recompute_initiative_coherence, initiative.id)
    return _redirect(f"/initiatives/{initiative.id}")


@initiatives_router.post("/{initiative_id}/members/{campaign_id}/remove")
async def remove_member(
    initiative_id: uuid.UUID,
    campaign_id: uuid.UUID,
    background_tasks: BackgroundTasks,
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
        await session.commit()
        background_tasks.add_task(_recompute_initiative_coherence, initiative.id)

    return _redirect(f"/initiatives/{initiative.id}")


# --- Events (SSE) ------------------------------------------------------

events_router = APIRouter(prefix="/events", tags=["events"])


@events_router.get("/canvas")
async def canvas_events(identity: Identity = Depends(get_identity)):
    """Single SSE channel for the canvas module (arch-03). Read access is
    global (arch-02), so any authenticated user may subscribe.
    """
    return EventSourceResponse(events.canvas_channel.stream())
