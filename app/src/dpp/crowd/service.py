import math
import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dpp.campaign.models import Campaign, CampaignStatus
from dpp.crowd.models import Question, Questionnaire, QuestionnaireStatus, Response
from dpp.crowd.scrubber import scrub_text


class CrowdError(ValueError):
    pass


def parse_questions(form) -> list[dict]:
    prompts = form.getlist("prompt")
    types = form.getlist("question_type")
    required = form.getlist("required")
    option_values = form.getlist("options")
    if not 1 <= len(prompts) <= 5 or len(prompts) != len(types):
        raise CrowdError("Ein Fragebogen braucht ein bis fünf Fragen.")
    questions = []
    for index, (raw_prompt, question_type) in enumerate(zip(prompts, types, strict=True)):
        prompt = str(raw_prompt).strip()
        if not prompt or len(prompt) > 200 or question_type not in {"text", "single_choice", "multiple_choice"}:
            raise CrowdError("Bitte prüfe Fragetext und Fragetyp.")
        raw_options = option_values[index] if index < len(option_values) else ""
        options = []
        if question_type != "text":
            labels = [line.strip() for line in str(raw_options).splitlines() if line.strip()]
            if not 2 <= len(labels) <= 8 or any(len(label) > 80 for label in labels):
                raise CrowdError("Auswahlfragen brauchen zwei bis acht Antwortoptionen (max. 80 Zeichen).")
            options = [{"id": str(uuid.uuid4()), "label": label} for label in labels]
        questions.append({
            "position": index + 1,
            "prompt": prompt,
            "question_type": question_type,
            "required": str(index) in required,
            "options": options,
        })
    return questions


def set_definition(questionnaire: Questionnaire, title: str, intro: str, questions: list[dict]) -> None:
    title = title.strip()
    intro = intro.strip()
    if not title or len(title) > 100 or len(intro) > 500:
        raise CrowdError("Bitte prüfe Titel und Einleitung.")
    if questionnaire.status != QuestionnaireStatus.DRAFT:
        raise CrowdError("Aktive und geschlossene Fragebögen können nicht inhaltlich geändert werden.")
    questionnaire.title = title
    questionnaire.intro = intro or None
    questionnaire.questions.clear()
    questionnaire.questions.extend(Question(**q) for q in questions)


def is_collectable(questionnaire: Questionnaire) -> bool:
    """Active is the sole public collection state; campaign changes close it explicitly."""
    return questionnaire.status == QuestionnaireStatus.ACTIVE


def activate(questionnaire: Questionnaire, campaign: Campaign | None = None) -> None:
    if questionnaire.status == QuestionnaireStatus.ACTIVE:
        raise CrowdError("Der Fragebogen ist bereits aktiv.")
    if not 1 <= len(questionnaire.questions) <= 5:
        raise CrowdError("Ein Fragebogen braucht ein bis fünf Fragen.")
    if (questionnaire.campaign_id is not None or campaign is not None) and (
        campaign is None or campaign.status != CampaignStatus.RUNNING
    ):
        raise CrowdError("Die verknüpfte Kampagne muss laufen, bevor der Fragebogen aktiviert werden kann.")
    questionnaire.status = QuestionnaireStatus.ACTIVE
    questionnaire.collection_started_at = datetime.now(UTC)
    questionnaire.collection_stopped_at = None


def close(questionnaire: Questionnaire, now: datetime | None = None) -> None:
    if questionnaire.status == QuestionnaireStatus.ACTIVE:
        questionnaire.collection_stopped_at = now or datetime.now(UTC)
    questionnaire.status = QuestionnaireStatus.CLOSED


def duplicate(
    questionnaire: Questionnaire, created_by: str, campaign: Campaign | None = None
) -> Questionnaire:
    campaign_id = (
        questionnaire.campaign_id
        if campaign is not None and campaign.status in {CampaignStatus.DRAFT, CampaignStatus.REVIEW, CampaignStatus.RUNNING}
        else None
    )
    clone = Questionnaire(
        title=f"{questionnaire.title[:90]} (Kopie)",
        intro=questionnaire.intro,
        created_by=created_by,
        campaign_id=campaign_id,
        questions=[
            Question(
                position=q.position,
                prompt=q.prompt,
                question_type=q.question_type,
                required=q.required,
                options=[dict(option) for option in q.options],
            )
            for q in questionnaire.questions
        ],
    )
    return clone


async def close_active_questionnaires_for_campaign(
    session: AsyncSession, campaign_id: uuid.UUID, now: datetime | None = None
) -> list[uuid.UUID]:
    stopped_at = now or datetime.now(UTC)
    result = await session.execute(
        select(Questionnaire).where(
            Questionnaire.campaign_id == campaign_id,
            Questionnaire.status == QuestionnaireStatus.ACTIVE,
        )
    )
    questionnaires = list(result.scalars())
    for questionnaire in questionnaires:
        close(questionnaire, stopped_at)
    return [questionnaire.id for questionnaire in questionnaires]


async def load_by_token(session: AsyncSession, token: str) -> Questionnaire | None:
    result = await session.execute(
        select(Questionnaire)
        .options(selectinload(Questionnaire.questions))
        .where(Questionnaire.token == token)
    )
    return result.scalar_one_or_none()


def _answer_payload(question: Question, answer) -> dict | None:
    if question.question_type == "text":
        if answer is not None and not isinstance(answer, (str, dict)):
            raise CrowdError("Ungültige Freitextantwort.")
        raw_text = answer.get("text", "") if isinstance(answer, dict) else answer
        if not isinstance(raw_text, str):
            raise CrowdError("Ungültige Freitextantwort.")
        text = str(raw_text or "").strip()
        if len(text) > 500:
            raise CrowdError("Freitext darf höchstens 500 Zeichen lang sein.")
        return {"text": scrub_text(text), "options": [], "via_voice": False} if text else None
    if question.question_type == "single_choice":
        ids = [str(answer)] if answer else []
    else:
        ids = answer if isinstance(answer, list) else []
        ids = [str(value) for value in ids]
    allowed = {str(option["id"]) for option in question.options}
    if any(value not in allowed for value in ids) or (question.question_type == "single_choice" and len(ids) > 1):
        raise CrowdError("Ungültige Auswahl.")
    if len(set(ids)) != len(ids):
        raise CrowdError("Antwortoptionen dürfen nicht doppelt gewählt werden.")
    return {"text": None, "options": ids, "via_voice": False} if ids else None


async def save_response(session: AsyncSession, questionnaire: Questionnaire, payload: dict) -> tuple[Response, bool]:
    try:
        client_id = uuid.UUID(str(payload["client_id"]))
        captured_at = datetime.fromisoformat(str(payload["captured_at"]))
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
        accuracy = float(payload["accuracy_m"])
    except (KeyError, ValueError, TypeError) as exc:
        raise CrowdError("Ungültige Antwortdaten oder Standortangaben.") from exc
    if (
        captured_at.tzinfo is None
        or not all(math.isfinite(value) for value in (latitude, longitude, accuracy))
        or abs(latitude) > 90
        or abs(longitude) > 180
        or accuracy < 0
        or accuracy > 100
    ):
        raise CrowdError("Der Standort ist ungenau oder ungültig. Bitte erneut versuchen.")
    latitude = round(latitude, 4)
    longitude = round(longitude, 4)
    existing = await session.scalar(
        select(Response).where(Response.questionnaire_id == questionnaire.id, Response.client_id == client_id)
    )
    if existing:
        return existing, False
    stopped_at = questionnaire.collection_stopped_at
    started_at = questionnaire.collection_started_at
    if started_at and captured_at < started_at:
        raise CrowdError("Die Antwort wurde vor Beginn der aktuellen Befragung aufgenommen.")
    if questionnaire.status == QuestionnaireStatus.ACTIVE:
        pass
    elif questionnaire.status == QuestionnaireStatus.CLOSED and stopped_at is not None and captured_at <= stopped_at:
        # Accept delayed offline sync from the just-closed collection window.
        pass
    else:
        raise CrowdError("Die Umfrage ist nicht mehr aktiv.")
    if captured_at > datetime.now(UTC) + timedelta(minutes=5):
        raise CrowdError("Ungültiger Zeitstempel.")

    submitted = payload.get("answers", {})
    if not isinstance(submitted, dict):
        raise CrowdError("Ungültige Antworten.")
    answers = {}
    for question in questionnaire.questions:
        raw = submitted.get(str(question.id))
        answer = _answer_payload(question, raw)
        if question.required and answer is None:
            raise CrowdError("Bitte beantworte alle Pflichtfragen.")
        if answer is not None:
            # Voice marker is client data but can only add provenance, not alter the stored answer.
            answer["via_voice"] = bool(isinstance(raw, dict) and raw.get("via_voice"))
            answers[str(question.id)] = answer
    unknown_questions = set(submitted) - {str(q.id) for q in questionnaire.questions}
    if unknown_questions:
        raise CrowdError("Die Antwort enthält unbekannte Fragen.")
    response = Response(
        questionnaire_id=questionnaire.id,
        client_id=client_id,
        location=WKTElement(f"POINT({longitude} {latitude})", srid=4326),
        accuracy_m=accuracy,
        captured_at=captured_at,
        answers=answers,
    )
    session.add(response)
    await session.flush()
    return response, True


async def response_count(session: AsyncSession, questionnaire_id: uuid.UUID) -> int:
    return int(await session.scalar(select(func.count(Response.id)).where(Response.questionnaire_id == questionnaire_id)) or 0)
