import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from dpp.campaign.models import Campaign, CampaignStatus, District
from dpp.crowd.events import crowd_channel
from dpp.crowd.models import Question, Questionnaire, QuestionnaireStatus, Response
from dpp.crowd.scrubber import scrub_text
from dpp.crowd.service import (
    CrowdError,
    activate,
    close,
    save_response,
)
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


def questionnaire_fixture(campaign=None):
    q = Questionnaire(title="Kiez und Grün", created_by="campaigner", campaign=campaign)
    q.questions = [
        Question(position=1, prompt="Was sollte besser werden?", question_type="text", required=True, options=[]),
        Question(
            position=2,
            prompt="Wie oft nutzt du den Park?",
            question_type="single_choice",
            required=False,
            options=[{"id": "park-often", "label": "Oft"}, {"id": "park-sometimes", "label": "Manchmal"}],
        ),
    ]
    activate(q, campaign)
    return q


async def test_scrubber_redacts_common_german_direct_identifiers():
    value = "Mail an test@example.org, Telefon 030 12345678, IBAN DE89 3704 0044 0532 0130 00, https://example.org, Hauptstraße 12, 10999 Berlin"
    cleaned = scrub_text(value)
    assert "test@example.org" not in cleaned
    assert "030 12345678" not in cleaned
    assert "DE89" not in cleaned
    assert "https://example.org" not in cleaned
    assert "Hauptstraße 12" not in cleaned
    assert "[E-Mail]" in cleaned
    assert "[Telefon]" in cleaned
    assert "[IBAN]" in cleaned
    assert "[URL]" in cleaned
    assert "[Adresse]" in cleaned


async def test_public_questionnaire_page_and_answer_submission(client, db_session):
    district = District(name="Kreuzberg")
    campaign = Campaign(district=district, status=CampaignStatus.RUNNING, thema="Kiezgrün")
    q = questionnaire_fixture(campaign)
    question_text, question_choice = q.questions
    db_session.add(q)
    await db_session.commit()

    public_page = await client.get(f"/crowd/r/{q.token}")
    assert public_page.status_code == 200
    assert "Kiez und Grün" in public_page.text
    assert "Navigation" not in public_page.text
    assert "Standort" in public_page.text

    response = await client.post(
        f"/crowd/api/r/{q.token}/responses",
        json={
            "client_id": str(uuid.uuid4()),
            "captured_at": datetime.now(UTC).isoformat(),
            "latitude": 52.52341,
            "longitude": 13.40126,
            "accuracy_m": 10,
            "answers": {
                str(question_text.id): {"text": "Ruft mich unter 030 12345678 an", "via_voice": False},
                str(question_choice.id): "park-often",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    saved = await db_session.scalar(select(Response).where(Response.questionnaire_id == q.id))
    assert "030 12345678" not in saved.answers[str(question_text.id)]["text"]
    coords = (await db_session.execute(text("SELECT ST_X(location::geometry), ST_Y(location::geometry) FROM crowd_responses"))).one()
    assert coords == (13.4013, 52.5234)

    duplicate = await client.post(f"/crowd/api/r/{q.token}/responses", json={
        "client_id": str(saved.client_id),
        "captured_at": datetime.now(UTC).isoformat(), "latitude": 52.5234, "longitude": 13.4013, "accuracy_m": 10,
        "answers": {str(question_text.id): {"text": "another", "via_voice": False}, str(question_choice.id): "park-often"},
    })
    # Idempotency is scoped to a questionnaire and client UUID.
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    analysis = await client.get(
        "/crowd/api/analysis",
        params={"qid": str(q.id), "west": 13, "south": 52, "east": 14, "north": 53, "color_question_id": str(question_choice.id)},
        headers=auth_headers("analyst", set()),
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["aggregates"]["responses"] == 1
    assert analysis.json()["aggregates"]["choices"][0]["count"] == 1
    assert analysis.json()["features"][0]["properties"]["color_option"] == "park-often"


async def test_auth_required_for_admin_but_public_respondent_is_anonymous(client, db_session):
    assert (await client.get("/crowd/questionnaires")).status_code == 401
    assert (await client.get("/crowd/analysis")).status_code == 401
    district = District(name="Berlin")
    campaign = Campaign(district=district, status=CampaignStatus.RUNNING)
    q = questionnaire_fixture(campaign)
    db_session.add(q)
    await db_session.commit()
    public = await client.get(f"/crowd/r/{q.token}", headers={"X-User-Id": "spoofed"})
    assert public.status_code == 200
    admin = await client.get("/crowd/questionnaires", headers=auth_headers("viewer", set()))
    assert admin.status_code == 200
    analysis_page = await client.get("/crowd/analysis", headers=auth_headers("viewer", set()))
    assert analysis_page.status_code == 200
    assert "Geodatenanalyse" in analysis_page.text


async def test_creator_can_preview_draft_without_storage(client, db_session):
    q = Questionnaire(
        title="Vorschau",
        created_by="owner",
        questions=[Question(position=1, prompt="Deine Idee?", question_type="text", required=True, options=[])],
    )
    db_session.add(q)
    await db_session.commit()
    preview = await client.get(f"/crowd/questionnaires/{q.id}/preview", headers=auth_headers("owner", set()))
    assert preview.status_code == 200
    assert "Vorschau – Antworten werden nicht gespeichert" in preview.text
    assert 'data-preview="true"' in preview.text
    assert 'action="/crowd/api/' not in preview.text


async def test_authenticated_user_can_create_edit_and_activate_questionnaire(client):
    headers = auth_headers("creator", set())
    created = await client.post(
        "/crowd/questionnaires/new",
        content=urlencode([
            ("title", "Mein Fragebogen"),
            ("intro", "Kurze Einleitung"),
            ("prompt", "Was wünschst du dir?"),
            ("question_type", "text"),
            ("options", ""),
            ("required", "0"),
        ]),
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text
    qid = created.headers["location"].rsplit("/", 1)[1]
    edit = await client.get(f"/crowd/questionnaires/{qid}/edit", headers=headers)
    assert edit.status_code == 200
    detail = await client.get(f"/crowd/questionnaires/{qid}", headers=headers)
    assert "Was wünschst du dir?" in detail.text
    activated = await client.post(f"/crowd/questionnaires/{qid}/activate", headers=headers, follow_redirects=False)
    assert activated.status_code == 303


async def test_linked_activation_requires_running_campaign_and_dropdown_filters_closed(client, db_session):
    district = District(name="Pankow")
    draft = Campaign(district=district, status=CampaignStatus.DRAFT, thema="Planung")
    review = Campaign(district=district, status=CampaignStatus.REVIEW, thema="Prüfung")
    running = Campaign(district=district, status=CampaignStatus.RUNNING, thema="Laufend")
    finished = Campaign(district=district, status=CampaignStatus.FINISHED, thema="Beendet")
    q = Questionnaire(
        title="Parkbefragung",
        status=QuestionnaireStatus.DRAFT,
        created_by="owner",
        campaign=review,
        questions=[Question(position=1, prompt="Was wünschst du dir?", question_type="text", required=True, options=[])],
    )
    db_session.add_all([draft, review, running, finished, q])
    await db_session.commit()
    headers = auth_headers("owner", {str(district.id)})

    new_page = await client.get("/crowd/questionnaires/new", headers=headers)
    assert "Planung" in new_page.text and "Prüfung" in new_page.text and "Laufend" in new_page.text
    assert "Beendet" not in new_page.text
    detail = await client.get(f"/crowd/questionnaires/{q.id}", headers=headers)
    assert "Kampagne muss Laufend sein" in detail.text
    blocked = await client.post(f"/crowd/questionnaires/{q.id}/activate", headers=headers)
    assert blocked.status_code == 400

    started = await client.post(
        f"/campaigns/{review.id}/transition",
        data={"to_status": "running"},
        headers=headers,
        follow_redirects=False,
    )
    assert started.status_code == 303
    await db_session.refresh(q)
    assert q.status == QuestionnaireStatus.DRAFT
    activated = await client.post(f"/crowd/questionnaires/{q.id}/activate", headers=headers, follow_redirects=False)
    assert activated.status_code == 303

    active_edit = await client.get(f"/crowd/questionnaires/{q.id}/edit", headers=headers)
    assert active_edit.status_code == 200
    assert 'name="campaign_id"' in active_edit.text
    assert '<select id="campaign_id"' not in active_edit.text
    attempted_relink = await client.post(
        f"/crowd/questionnaires/{q.id}/edit",
        content=urlencode([("title", q.title), ("intro", ""), ("campaign_id", str(draft.id))]),
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert attempted_relink.status_code == 400
    await db_session.refresh(q)
    assert q.campaign_id == review.id


async def test_campaign_completion_closes_linked_active_questionnaires_and_publishes_event(client, db_session):
    district = District(name="Tempelhof")
    campaign = Campaign(district=district, status=CampaignStatus.RUNNING, thema="Stadtgrün")
    q = questionnaire_fixture(campaign)
    db_session.add(q)
    await db_session.commit()
    queue = crowd_channel.subscribe()
    try:
        response = await client.post(
            f"/campaigns/{campaign.id}/transition",
            data={"to_status": "finished"},
            headers=auth_headers("owner", {str(district.id)}),
            follow_redirects=False,
        )
        assert response.status_code == 303
        await db_session.refresh(q)
        assert q.status == QuestionnaireStatus.CLOSED
        assert q.collection_stopped_at is not None
        event = queue.get_nowait()
        assert event.event == "crowd.questionnaire_status_changed"
        assert event.data == {"questionnaire_id": str(q.id), "status": "closed"}
    finally:
        crowd_channel.unsubscribe(queue)


async def test_questionnaire_edit_is_creator_only_and_question_count_is_limited(client, db_session):
    q = Questionnaire(title="Test", created_by="owner")
    db_session.add(q)
    await db_session.commit()
    denied = await client.post(f"/crowd/questionnaires/{q.id}/activate", headers=auth_headers("other", set()))
    assert denied.status_code == 403
    q = await db_session.scalar(select(Questionnaire).options(selectinload(Questionnaire.questions)).where(Questionnaire.id == q.id))
    q.questions = [Question(position=i, prompt=f"Frage {i}", question_type="text", required=True, options=[]) for i in range(1, 6)]
    db_session.add(q)
    await db_session.commit()
    q.status = QuestionnaireStatus.DRAFT
    q.questions.append(Question(position=6, prompt="Zu viel", question_type="text", required=True, options=[]))
    db_session.add(q)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_offline_answer_sync_is_accepted_only_if_captured_before_collection_stopped(db_session):
    district = District(name="Mitte")
    campaign = Campaign(district=district, status=CampaignStatus.RUNNING)
    q = questionnaire_fixture(campaign)
    db_session.add(q)
    await db_session.commit()
    q = await db_session.scalar(select(Questionnaire).options(selectinload(Questionnaire.questions), selectinload(Questionnaire.campaign)).where(Questionnaire.id == q.id))
    captured = datetime.now(UTC)
    close(q, captured + timedelta(seconds=5))
    campaign.status = CampaignStatus.FINISHED
    await db_session.commit()
    before = {
        "client_id": str(uuid.uuid4()), "captured_at": captured.isoformat(), "latitude": 52.52, "longitude": 13.4,
        "accuracy_m": 8, "answers": {str(q.questions[0].id): {"text": "Grün", "via_voice": False}},
    }
    saved, created = await save_response(db_session, q, before)
    assert created and saved.id
    after = dict(before, client_id=str(uuid.uuid4()), captured_at=(q.collection_stopped_at + timedelta(seconds=1)).isoformat())
    with pytest.raises(CrowdError, match="nicht mehr aktiv"):
        await save_response(db_session, q, after)


async def test_linked_questionnaire_cannot_activate_before_campaign_runs():
    district = District(name="Neukölln")
    campaign = Campaign(district=district, status=CampaignStatus.REVIEW)
    q = Questionnaire(
        title="Vorbereitung",
        status=QuestionnaireStatus.DRAFT,
        created_by="owner",
        campaign=campaign,
        questions=[Question(position=1, prompt="Frage", question_type="text", required=True, options=[])],
    )
    with pytest.raises(CrowdError, match="muss laufen"):
        activate(q, campaign)
    assert q.status == QuestionnaireStatus.DRAFT
