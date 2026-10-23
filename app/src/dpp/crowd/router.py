import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from geoalchemy2 import Geometry
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse
from starlette import status

from dpp.auth.dependencies import ensure_write_access, get_identity
from dpp.auth.headers import Identity
from dpp.campaign.models import Campaign, CampaignStatus
from dpp.config import get_settings
from dpp.crowd import events, service
from dpp.crowd.models import Questionnaire, QuestionnaireStatus
from dpp.crowd.models import Response as CrowdResponse
from dpp.crowd.ratelimit import responses_limiter, transcribe_limiter
from dpp.crowd.transcribe import get_transcriber
from dpp.db import get_session
from dpp.templating import templates

admin_router = APIRouter(prefix="/crowd", tags=["crowd-admin"])
public_router = APIRouter(prefix="/crowd", tags=["crowd-public"])
LINKABLE_CAMPAIGN_STATUSES = (CampaignStatus.DRAFT, CampaignStatus.REVIEW, CampaignStatus.RUNNING)


def _campaign_choices(current_campaign_id: uuid.UUID | None = None):
    query = select(Campaign).options(selectinload(Campaign.district)).where(
        Campaign.status.in_(LINKABLE_CAMPAIGN_STATUSES)
    )
    if current_campaign_id is not None:
        query = query.where(or_(Campaign.status.in_(LINKABLE_CAMPAIGN_STATUSES), Campaign.id == current_campaign_id))
    return query.order_by(
        case(
            (Campaign.status == CampaignStatus.RUNNING, 0),
            (Campaign.status == CampaignStatus.REVIEW, 1),
            else_=2,
        ),
        Campaign.created_at.desc(),
    )


def _client_ip(request: Request) -> str:
    """Read the proxy-sanitized client IP; deployment must strip untrusted forwarding headers."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _redirect(path: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


async def _owned_questionnaire(session: AsyncSession, qid: uuid.UUID, identity: Identity) -> Questionnaire:
    q = await session.scalar(
        select(Questionnaire).options(selectinload(Questionnaire.questions), selectinload(Questionnaire.campaign))
        .where(Questionnaire.id == qid)
    )
    if q is None:
        raise HTTPException(404, "Fragebogen nicht gefunden.")
    if q.created_by != identity.user_id:
        raise HTTPException(403, "Nur die erstellende Person darf diesen Fragebogen verwalten.")
    return q


@admin_router.get("/questionnaires")
async def list_questionnaires(request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    result = await session.execute(
        select(Questionnaire).options(selectinload(Questionnaire.campaign)).order_by(Questionnaire.created_at.desc())
    )
    questionnaires = list(result.scalars().all())
    counts = {}
    for q in questionnaires:
        counts[q.id] = await service.response_count(session, q.id)
    return templates.TemplateResponse(request, "crowd/list.html", {"identity": identity, "questionnaires": questionnaires, "counts": counts})


@admin_router.get("/questionnaires/new")
async def new_questionnaire(request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    campaigns = list((await session.scalars(_campaign_choices())).all())
    return templates.TemplateResponse(request, "crowd/edit.html", {"identity": identity, "questionnaire": None, "campaigns": campaigns, "error": None, "question_data": []})


@admin_router.post("/questionnaires/new")
async def create_questionnaire(request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    form = await request.form()
    title, intro = str(form.get("title", "")), str(form.get("intro", ""))
    try:
        questions = service.parse_questions(form)
        q = Questionnaire(
            title=title.strip(),
            intro=intro.strip() or None,
            created_by=identity.user_id,
            status=QuestionnaireStatus.DRAFT,
        )
        service.set_definition(q, title, intro, questions)
        campaign_id = str(form.get("campaign_id", "")).strip()
        if campaign_id:
            campaign = await session.get(Campaign, uuid.UUID(campaign_id))
            if campaign is None:
                raise service.CrowdError("Kampagne nicht gefunden.")
            if campaign.status not in LINKABLE_CAMPAIGN_STATUSES:
                raise service.CrowdError("Mit abgeschlossenen Kampagnen kann kein Fragebogen verknüpft werden.")
            ensure_write_access(identity, campaign.district_id)
            q.campaign_id = campaign.id
        session.add(q)
        await session.commit()
    except (service.CrowdError, ValueError) as exc:
        await session.rollback()
        campaigns = list((await session.scalars(_campaign_choices())).all())
        return templates.TemplateResponse(request, "crowd/edit.html", {"identity": identity, "questionnaire": None, "campaigns": campaigns, "error": str(exc), "question_data": []}, status_code=400)
    return _redirect(f"/crowd/questionnaires/{q.id}")


@admin_router.get("/questionnaires/{qid}")
async def questionnaire_detail(qid: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await session.scalar(select(Questionnaire).options(selectinload(Questionnaire.questions), selectinload(Questionnaire.campaign)).where(Questionnaire.id == qid))
    if q is None:
        raise HTTPException(404, "Fragebogen nicht gefunden.")
    can_edit = q.created_by == identity.user_id
    can_activate = q.campaign is None or q.campaign.status == CampaignStatus.RUNNING
    return templates.TemplateResponse(request, "crowd/detail.html", {"identity": identity, "questionnaire": q, "count": await service.response_count(session, q.id), "can_edit": can_edit, "can_activate": can_activate, "public_url": str(request.base_url).rstrip("/") + f"/crowd/r/{q.token}"})


@admin_router.get("/questionnaires/{qid}/edit")
async def edit_questionnaire_page(qid: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await _owned_questionnaire(session, qid, identity)
    campaigns = list((await session.scalars(_campaign_choices(q.campaign_id))).all())
    question_data = [{"prompt": item.prompt, "question_type": item.question_type, "required": item.required, "options": item.options} for item in q.questions]
    return templates.TemplateResponse(request, "crowd/edit.html", {"identity": identity, "questionnaire": q, "campaigns": campaigns, "error": None, "question_data": question_data})


@admin_router.post("/questionnaires/{qid}/edit")
async def edit_questionnaire(qid: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await _owned_questionnaire(session, qid, identity)
    form = await request.form()
    try:
        if q.status == QuestionnaireStatus.DRAFT:
            service.set_definition(q, str(form.get("title", "")), str(form.get("intro", "")), service.parse_questions(form))
        else:
            title, intro = str(form.get("title", "")).strip(), str(form.get("intro", "")).strip()
            if not title or len(title) > 100 or len(intro) > 500:
                raise service.CrowdError("Bitte prüfe Titel und Einleitung.")
            q.title, q.intro = title, intro or None
        previous_campaign_id = q.campaign_id
        if q.status == QuestionnaireStatus.ACTIVE:
            campaign_raw = str(form.get("campaign_id", previous_campaign_id or "")).strip()
            if campaign_raw and uuid.UUID(campaign_raw) != previous_campaign_id:
                raise service.CrowdError("Die Kampagnenverknüpfung kann bei einem aktiven Fragebogen nicht geändert werden.")
        else:
            campaign_raw = str(form.get("campaign_id", "")).strip()
            campaign = await session.get(Campaign, uuid.UUID(campaign_raw)) if campaign_raw else None
            if campaign_raw and campaign is None:
                raise service.CrowdError("Kampagne nicht gefunden.")
            if campaign and campaign.id != previous_campaign_id:
                if campaign.status not in LINKABLE_CAMPAIGN_STATUSES:
                    raise service.CrowdError("Mit abgeschlossenen Kampagnen kann kein Fragebogen verknüpft werden.")
                ensure_write_access(identity, campaign.district_id)
            q.campaign_id = campaign.id if campaign else None
        await session.commit()
    except (service.CrowdError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from exc
    return _redirect(f"/crowd/questionnaires/{qid}")


@admin_router.get("/questionnaires/{qid}/preview")
async def preview_questionnaire(qid: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await _owned_questionnaire(session, qid, identity)
    question_data = [{"id": str(item.id), "type": item.question_type, "required": item.required} for item in q.questions]
    return templates.TemplateResponse(
        request,
        "crowd/respondent.html",
        {"questionnaire": q, "collectable": bool(q.questions), "transcribe_enabled": False, "question_data": question_data, "preview": True},
    )


@admin_router.post("/questionnaires/{qid}/activate")
async def activate_questionnaire(qid: uuid.UUID, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await _owned_questionnaire(session, qid, identity)
    campaign = None
    if q.campaign_id:
        campaign = await session.get(Campaign, q.campaign_id)
        if campaign is None:
            raise HTTPException(400, "Verknüpfte Kampagne nicht gefunden.")
        ensure_write_access(identity, campaign.district_id)
    try:
        service.activate(q, campaign)
    except service.CrowdError as exc:
        raise HTTPException(400, str(exc)) from exc
    await session.commit()
    await events.publish_questionnaire_status(str(q.id), q.status.value)
    return _redirect(f"/crowd/questionnaires/{qid}")


@admin_router.post("/questionnaires/{qid}/close")
async def close_questionnaire(qid: uuid.UUID, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await _owned_questionnaire(session, qid, identity)
    service.close(q)
    await session.commit()
    await events.publish_questionnaire_status(str(q.id), q.status.value)
    return _redirect(f"/crowd/questionnaires/{qid}")


@admin_router.post("/questionnaires/{qid}/duplicate")
async def duplicate_questionnaire(qid: uuid.UUID, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    source = await session.scalar(
        select(Questionnaire)
        .options(selectinload(Questionnaire.questions), selectinload(Questionnaire.campaign))
        .where(Questionnaire.id == qid)
    )
    if source is None:
        raise HTTPException(404, "Fragebogen nicht gefunden.")
    clone = service.duplicate(source, identity.user_id, source.campaign)
    session.add(clone)
    await session.commit()
    return _redirect(f"/crowd/questionnaires/{clone.id}")


@admin_router.post("/questionnaires/{qid}/delete")
async def delete_questionnaire(qid: uuid.UUID, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await _owned_questionnaire(session, qid, identity)
    if await service.response_count(session, q.id):
        service.close(q)
    else:
        await session.delete(q)
    await session.commit()
    return _redirect("/crowd/questionnaires")


@admin_router.get("/analysis")
async def analysis_page(request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    questionnaires = list((await session.scalars(select(Questionnaire).options(selectinload(Questionnaire.campaign), selectinload(Questionnaire.questions)).order_by(Questionnaire.title))).all())
    campaigns = list((await session.scalars(select(Campaign).order_by(Campaign.created_at.desc()))).all())
    return templates.TemplateResponse(request, "crowd/analysis.html", {"identity": identity, "questionnaires": questionnaires, "campaigns": campaigns, "config_tile_url": get_settings().map_tile_url})


@admin_router.get("/api/analysis")
async def analysis_data(qid: uuid.UUID, west: float, south: float, east: float, north: float, campaign_id: uuid.UUID | None = None, start: str = "", end: str = "", color_question_id: uuid.UUID | None = None, text_page: int = 1, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(422, "Ungültiger Kartenausschnitt.")
    q = await session.scalar(select(Questionnaire).options(selectinload(Questionnaire.questions)).where(Questionnaire.id == qid))
    if q is None:
        raise HTTPException(404, "Fragebogen nicht gefunden.")
    clauses = [CrowdResponse.questionnaire_id == qid]
    if campaign_id:
        linked_campaign = await session.scalar(select(Questionnaire.campaign_id).where(Questionnaire.id == qid))
        if linked_campaign != campaign_id:
            return {"features": [], "total": 0, "aggregates": {}}
    try:
        if start:
            start_at = datetime.fromisoformat(start)
            clauses.append(CrowdResponse.received_at >= (start_at.replace(tzinfo=UTC) if start_at.tzinfo is None else start_at))
        if end:
            end_at = datetime.fromisoformat(end)
            clauses.append(CrowdResponse.received_at < (end_at.replace(tzinfo=UTC) if end_at.tzinfo is None else end_at))
    except ValueError as exc:
        raise HTTPException(422, "Ungültiger Zeitraum.") from exc
    clauses.append(text("crowd_responses.location && ST_MakeEnvelope(:west, :south, :east, :north, 4326)::geography"))
    bounds = {"west": west, "south": south, "east": east, "north": north}
    total = int(await session.scalar(select(func.count(CrowdResponse.id)).where(*clauses).params(**bounds)) or 0)
    stmt = select(
        CrowdResponse.id, CrowdResponse.answers, CrowdResponse.received_at,
        func.ST_X(CrowdResponse.location.cast(Geometry(geometry_type="POINT", srid=4326))).label("lon"),
        func.ST_Y(CrowdResponse.location.cast(Geometry(geometry_type="POINT", srid=4326))).label("lat"),
    ).where(*clauses).params(**bounds).limit(10001)
    rows = list((await session.execute(stmt)).mappings().all())
    rows = rows[:10000]
    selected_question = next((question for question in q.questions if question.id == color_question_id), None)
    if selected_question and selected_question.question_type != "single_choice":
        raise HTTPException(422, "Nur Einzelauswahlfragen können zur Färbung verwendet werden.")
    choice_counts: dict[str, dict[str, int]] = {}
    text_answers = []
    for row in rows:
        for question in q.questions:
            answer = row["answers"].get(str(question.id))
            if not answer:
                continue
            if question.question_type in {"single_choice", "multiple_choice"}:
                for option_id in answer.get("options", []):
                    question_counts = choice_counts.setdefault(str(question.id), {})
                    question_counts[option_id] = question_counts.get(option_id, 0) + 1
            elif answer.get("text"):
                text_answers.append({"question": question.prompt, "text": answer["text"], "lat": row["lat"], "lon": row["lon"]})
    features = []
    for row in rows:
        selected_option = None
        if selected_question:
            answer = row["answers"].get(str(selected_question.id), {})
            selected_option = answer.get("options", [None])[0]
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]}, "properties": {"id": str(row["id"]), "received_at": row["received_at"].isoformat(), "answers": row["answers"], "color_option": selected_option}})
    choices = []
    for question in q.questions:
        if question.question_type not in {"single_choice", "multiple_choice"}:
            continue
        counts = choice_counts.get(str(question.id), {})
        choices.extend({"question": question.prompt, "question_id": str(question.id), "id": option["id"], "label": option["label"], "count": counts.get(option["id"], 0)} for option in question.options)
    text_pages = max(1, (len(text_answers) + 99) // 100)
    text_page = min(text_page, text_pages)
    first_text = (text_page - 1) * 100
    aggregates = {
        "responses": total,
        "choices": choices,
        "texts": text_answers[first_text : first_text + 100],
        "text_page": text_page,
        "text_pages": text_pages,
        "truncated": total > 10000,
    }
    return {"type": "FeatureCollection", "features": features, "total": total, "aggregates": aggregates, "question_id": str(selected_question.id) if selected_question else None}


@admin_router.get("/events")
async def crowd_events(identity: Identity = Depends(get_identity)):
    return EventSourceResponse(events.crowd_channel.stream())


@admin_router.get("/questionnaires/{qid}/qr.svg")
async def questionnaire_qr(qid: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session), identity: Identity = Depends(get_identity)):
    q = await session.get(Questionnaire, qid)
    if q is None:
        raise HTTPException(404)
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(str(request.base_url).rstrip("/") + f"/crowd/r/{q.token}", image_factory=SvgPathImage)
    return Response(image.to_string(encoding="unicode"), media_type="image/svg+xml")


@public_router.get("/r/sw.js")
async def service_worker():
    from pathlib import Path
    path = Path(__file__).parent.parent / "static" / "crowd" / "sw.js"
    return Response(path.read_text(), media_type="application/javascript", headers={"Service-Worker-Allowed": "/crowd/r/", "Cache-Control": "no-cache"})


@public_router.get("/r/{token}", name="respondent_app")
async def respondent_app(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    q = await service.load_by_token(session, token)
    if q is None:
        raise HTTPException(404, "Umfrage nicht gefunden.")
    collectable = service.is_collectable(q)
    question_data = [{"id": str(item.id), "type": item.question_type, "required": item.required} for item in q.questions] if collectable else []
    return templates.TemplateResponse(request, "crowd/respondent.html", {"questionnaire": q, "collectable": collectable, "transcribe_enabled": bool(get_settings().openai_api_key), "question_data": question_data, "preview": False})


@public_router.get("/r/{token}/manifest.webmanifest")
async def respondent_manifest(token: str, session: AsyncSession = Depends(get_session)):
    if not await service.load_by_token(session, token):
        raise HTTPException(404)
    return JSONResponse({"name": "Bürgerbefragung", "short_name": "Befragung", "start_url": f"/crowd/r/{token}", "display": "fullscreen", "background_color": "#032d67", "theme_color": "#032d67"}, media_type="application/manifest+json")


@public_router.post("/api/r/{token}/responses")
async def submit_response(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    ip = _client_ip(request)
    if not responses_limiter.allow(ip):
        raise HTTPException(429, "Zu viele Antworten. Bitte kurz warten.")
    q = await service.load_by_token(session, token)
    if q is None:
        raise HTTPException(404, "Umfrage nicht gefunden.")
    try:
        body_parts = []
        body_size = 0
        async for part in request.stream():
            body_size += len(part)
            if body_size > 32768:
                raise HTTPException(413, "Antwort ist zu groß.")
            body_parts.append(part)
        raw_payload = b"".join(body_parts)
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise service.CrowdError("Ungültige Antwortdaten.")
        response, created = await service.save_response(session, q, payload)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(select(CrowdResponse).where(
                CrowdResponse.questionnaire_id == q.id,
                CrowdResponse.client_id == uuid.UUID(str(payload["client_id"])),
            ))
            if existing is None:
                raise
            response, created = existing, False
    except service.CrowdError as exc:
        await session.rollback()
        raise HTTPException(410 if "nicht mehr aktiv" in str(exc) else 422, str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        await session.rollback()
        raise HTTPException(400, "Ungültige Antwortdaten.") from exc
    total = await service.response_count(session, q.id)
    if created:
        await events.publish_response_received(str(q.id), total)
    return {"id": str(response.id), "accepted": True, "duplicate": not created}


@public_router.post("/api/r/{token}/transcribe")
async def transcribe(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    ip = _client_ip(request)
    if not transcribe_limiter.allow(ip):
        raise HTTPException(429, "Zu viele Transkriptionsanfragen.")
    q = await service.load_by_token(session, token)
    if q is None or not service.is_collectable(q):
        raise HTTPException(410, "Die Umfrage ist nicht aktiv.")
    transcriber = get_transcriber()
    if transcriber is None:
        raise HTTPException(503, "Spracheingabe ist derzeit nicht verfügbar.")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    extensions = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/mpeg": "mp3"}
    if content_type not in extensions:
        raise HTTPException(415, "Dieses Audioformat wird nicht unterstützt.")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 5 * 1024 * 1024:
            raise HTTPException(413, "Audio muss kleiner als 5 MB sein.")
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    if not audio_bytes or len(audio_bytes) > 5 * 1024 * 1024:
        raise HTTPException(413, "Audio muss kleiner als 5 MB sein.")
    try:
        result = await transcriber.transcribe(audio_bytes, f"recording.{extensions[content_type]}", content_type)
    except Exception as exc:
        raise HTTPException(502, "Transkription fehlgeschlagen.") from exc
    return {"text": result[:500]}
