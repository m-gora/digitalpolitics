import uuid
from collections import Counter
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

import dpp.campaign.coherence as coherence_module
from dpp.campaign import events
from dpp.campaign.models import Campaign, Initiative
from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio

KEYWORDS = ["wohnen", "verkehr", "mobilisieren"]


def _topic(text: str) -> str:
    lower = (text or "").lower()
    return next((kw for kw in KEYWORDS if kw in lower), lower)


def _rubric_level(topics: list[str]) -> float:
    return 4.0 if len(set(topics)) == 1 else 0.0


class FakeTypeSafe:
    """Deterministic stand-in for TypeSafe: identical topics score 4 (1.00), differing topics 0."""

    def __init__(self):
        self.calls: list[dict] = []
        self.unavailable = False

    async def __call__(self, state, questions):
        self.calls.append({"state": state, "questions": questions})
        if self.unavailable:
            return None
        campaigns = state["campaigns"]
        scores = {}
        if "domain_similarity" in questions:
            topics = [_topic(c["thema"]) for c in campaigns if c["thema"]]
            scores["domain_similarity"] = SimpleNamespace(score=_rubric_level(topics))
        if "narrative_similarity" in questions:
            topics = [_topic(c["ziel"] or c["storytelling"]) for c in campaigns if c["ziel"] or c["storytelling"]]
            scores["narrative_similarity"] = SimpleNamespace(score=_rubric_level(topics))
        choices = {}
        if "initiative_outlier" in questions:
            counts = Counter(_topic(c["thema"]) for c in campaigns)
            lone = [c["id"] for c in campaigns if counts[_topic(c["thema"])] == 1]
            majority = len(counts) == 2 and len(lone) == 1
            choices["initiative_outlier"] = SimpleNamespace(choice=lone[0] if majority else "none_clear")
        return SimpleNamespace(scores=scores, choices=choices)


@pytest.fixture(autouse=True)
def typesafe(monkeypatch) -> FakeTypeSafe:
    fake = FakeTypeSafe()
    monkeypatch.setattr(coherence_module, "_ask_typesafe", fake)
    return fake


async def test_similarity_inputs_exclude_operational_fields():
    campaign = Campaign(
        id=uuid.uuid4(),
        district_id=uuid.uuid4(),
        thema="Bezahlbares Wohnen",
        ziel="Mehr Wohnungen schaffen",
        storytelling="Stimmen aus dem Kiez",
        zielgruppen="Mieter:innen",
        kanaele="Infostände",
        tools="Kontaktformular",
        phasen_flow="Infostand, Auswertung, Kampagnenstart",
    )
    initiative = Initiative(name="Wohnen", description="Gemeinsame Botschaft")

    state = coherence_module.typesafe_state(initiative, {"C1": campaign})

    assert state == {
        "initiative": {"name": "Wohnen", "description": "Gemeinsame Botschaft"},
        "campaigns": [
            {
                "id": "C1",
                "thema": "Bezahlbares Wohnen",
                "ziel": "Mehr Wohnungen schaffen",
                "storytelling": "Stimmen aus dem Kiez",
            }
        ],
    }


async def _create_campaign(client, district_id: str, headers: dict, thema: str, ziel: str) -> str:
    resp = await client.post("/campaigns", data={"district_id": district_id}, headers=headers)
    campaign_id = resp.headers["location"].rsplit("/", 1)[-1]
    resp = await client.post(
        f"/campaigns/{campaign_id}/fields", data={"thema": thema, "ziel": ziel}, headers=headers
    )
    assert resp.status_code == 303
    return campaign_id


async def test_initiative_accepts_campaigns_from_descendants_and_shows_member_districts(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    bv_fk = await make_district(db_session, "BV Friedrichshain-Kreuzberg", parent=berlin)
    ov_kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=bv_fk)
    headers = auth_headers("anna", {str(berlin.id), str(bv_fk.id), str(ov_kreuzberg.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(berlin.id), "name": "Bauen und Wohnen"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]

    bv_campaign = await _create_campaign(client, str(bv_fk.id), headers, "Mietendeckel", "Mehr bezahlbarer Wohnraum")
    ov_campaign = await _create_campaign(client, str(ov_kreuzberg.id), headers, "Leerstand melden", "Wohnraum nutzen")

    for campaign_id in (bv_campaign, ov_campaign):
        resp = await client.post(
            f"/initiatives/{initiative_id}/members",
            data={"campaign_id": campaign_id},
            headers=headers,
        )
        assert resp.status_code == 303

    list_response = await client.get("/initiatives", headers=headers)
    assert "BV Friedrichshain-Kreuzberg" in list_response.text
    assert "OV Kreuzberg" in list_response.text

    detail_response = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Koordiniert von LV Berlin" in detail_response.text
    assert f'data-initiative-id="{initiative_id}"' in detail_response.text
    assert "BV Friedrichshain-Kreuzberg" in detail_response.text
    assert "OV Kreuzberg" in detail_response.text


async def test_initiative_rejects_campaign_from_sibling_branch(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    bv_fk = await make_district(db_session, "BV Friedrichshain-Kreuzberg", parent=berlin)
    ov_kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=bv_fk)
    bv_mitte = await make_district(db_session, "BV Mitte", parent=berlin)
    headers = auth_headers("anna", {str(berlin.id), str(bv_fk.id), str(ov_kreuzberg.id), str(bv_mitte.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(bv_fk.id), "name": "Kiezwohnen"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]
    sibling_campaign = await _create_campaign(client, str(bv_mitte.id), headers, "Mitte Wohnen", "Ziel Mitte")

    resp = await client.post(
        f"/initiatives/{initiative_id}/members", data={"campaign_id": sibling_campaign}, headers=headers
    )
    assert resp.status_code == 400


async def test_initiative_edit_and_delete_preserve_campaigns(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("coordinator", {str(berlin.id)})
    outsider = auth_headers("outsider", set())
    campaign_id = await _create_campaign(client, str(berlin.id), headers, "Wohnen", "Bezahlbar wohnen")

    create_response = await client.post(
        "/initiatives",
        data={"district_id": str(berlin.id), "name": "Wohnen", "description": "Gemeinsame Botschaft"},
        headers=headers,
    )
    initiative_id = create_response.headers["location"].rsplit("/", 1)[-1]
    await client.post(
        f"/initiatives/{initiative_id}/members", data={"campaign_id": campaign_id}, headers=headers
    )

    denied = await client.post(
        f"/initiatives/{initiative_id}/edit",
        data={"name": "Nicht erlaubt", "description": ""},
        headers=outsider,
    )
    assert denied.status_code == 403

    edited = await client.post(
        f"/initiatives/{initiative_id}/edit",
        data={"name": "Bauen und Wohnen", "description": "Gemeinsame Berliner Botschaft"},
        headers=headers,
    )
    assert edited.status_code == 303
    detail = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Bauen und Wohnen" in detail.text
    assert "Gemeinsame Berliner Botschaft" in detail.text
    assert f"initiative-editor-{initiative_id}" in detail.text

    denied_delete = await client.post(f"/initiatives/{initiative_id}/delete", headers=outsider)
    assert denied_delete.status_code == 403
    deleted = await client.post(f"/initiatives/{initiative_id}/delete", headers=headers)
    assert deleted.status_code == 303

    # Removing the grouping does not delete its campaign.
    campaign_detail = await client.get(f"/campaigns/{campaign_id}", headers=headers)
    assert campaign_detail.status_code == 200
    assert "Wohnen" in campaign_detail.text
    assert f'id="campaign-field-help-{campaign_id}-thema"' in campaign_detail.text
    assert 'aria-label="Erklärung zu Thema"' in campaign_detail.text
    assert 'role="tooltip" hidden>Worum geht es?</span>' in campaign_detail.text


async def test_initiative_create_edit_and_delete_are_published(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("coordinator", {str(berlin.id)})
    subscriber = events.canvas_channel.subscribe()
    try:
        created = await client.post(
            "/initiatives", data={"district_id": str(berlin.id), "name": "Wohnen"}, headers=headers
        )
        initiative_id = created.headers["location"].rsplit("/", 1)[-1]
        event = subscriber.get_nowait()
        assert event.event == "initiative.updated"
        assert event.data == {"initiative_id": initiative_id, "change": "created"}

        edited = await client.post(
            f"/initiatives/{initiative_id}/edit",
            data={"name": "Bauen und Wohnen", "description": "Gemeinsame Botschaft"},
            headers=headers,
        )
        assert edited.status_code == 303
        event = subscriber.get_nowait()
        assert event.event == "initiative.updated"
        assert event.data == {"initiative_id": initiative_id, "change": "updated"}
        assert subscriber.get_nowait().event == "initiative.coherence_updated"

        deleted = await client.post(f"/initiatives/{initiative_id}/delete", headers=headers)
        assert deleted.status_code == 303
        event = subscriber.get_nowait()
        assert event.event == "initiative.updated"
        assert event.data == {"initiative_id": initiative_id, "change": "deleted"}
    finally:
        events.canvas_channel.unsubscribe(subscriber)


async def _create_initiative(client, district_id: str, headers: dict, name: str, description: str = "") -> str:
    resp = await client.post(
        "/initiatives",
        data={"district_id": district_id, "name": name, "description": description},
        headers=headers,
    )
    return resp.headers["location"].rsplit("/", 1)[-1]


async def _add_member(client, initiative_id: str, campaign_id: str, headers: dict) -> None:
    resp = await client.post(
        f"/initiatives/{initiative_id}/members", data={"campaign_id": campaign_id}, headers=headers
    )
    assert resp.status_code == 303


async def test_initiative_shows_separate_domain_and_narrative_scores(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Bauen und Wohnen")

    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen Kampagne 1", "Mehr wohnen schaffen")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen Kampagne 2", "Auch mehr wohnen schaffen")
    await _add_member(client, initiative_id, c1, headers)
    await _add_member(client, initiative_id, c2, headers)

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert resp.text.count('text-3xl font-black text-brand-cyan">1.00</p>') == 2
    assert f'id="initiative-domain-help-{initiative_id}"' in resp.text
    assert f'id="initiative-narrative-help-{initiative_id}"' in resp.text
    assert 'aria-label="Erklärung zu Domainähnlichkeit"' in resp.text
    assert 'role="tooltip" hidden>' in resp.text
    assert "Ausreißer-Kandidat</span>" not in resp.text

    # A third, thematically unrelated campaign lowers both scores and becomes the outlier candidate.
    c3 = await _create_campaign(client, str(berlin.id), headers, "Verkehr Kampagne", "Weniger Autos im Kiez")
    await _add_member(client, initiative_id, c3, headers)

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert resp.text.count('text-3xl font-black text-brand-cyan">0.00</p>') == 2
    assert resp.text.count("Ausreißer-Kandidat</span>") == 1
    assert resp.text.count("Kampagnen in dieser Initiative") == 1
    assert "aus Initiative entfernen" in resp.text

    initiative = await db_session.get(Initiative, uuid.UUID(initiative_id))
    await db_session.refresh(initiative)
    assert initiative.outlier_campaign_id == uuid.UUID(c3)


async def test_member_changes_and_recomputed_scores_are_published(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Bauen und Wohnen")
    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen Kampagne 1", "Mehr wohnen schaffen")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen Kampagne 2", "Auch mehr wohnen schaffen")

    subscriber = events.canvas_channel.subscribe()
    try:
        await _add_member(client, initiative_id, c1, headers)
        first_change = subscriber.get_nowait()
        assert first_change.event == "initiative.updated"
        assert first_change.data == {"initiative_id": initiative_id, "change": "member_added"}
        # A single scorable member refreshes the unavailable scores to None.
        assert subscriber.get_nowait().event == "initiative.coherence_updated"

        await _add_member(client, initiative_id, c2, headers)
        second_change = subscriber.get_nowait()
        coherence_update = subscriber.get_nowait()
        assert second_change.event == "initiative.updated"
        assert second_change.data == {"initiative_id": initiative_id, "change": "member_added"}
        assert coherence_update.event == "initiative.coherence_updated"
        assert coherence_update.data["initiative_id"] == initiative_id
        assert coherence_update.data["domain_similarity_score"] == 1.0
        assert coherence_update.data["narrative_similarity_score"] == 1.0

        removed = await client.post(f"/initiatives/{initiative_id}/members/{c2}/remove", headers=headers)
        assert removed.status_code == 303
        removal = subscriber.get_nowait()
        removal_coherence = subscriber.get_nowait()
        assert removal.event == "initiative.updated"
        assert removal.data == {"initiative_id": initiative_id, "change": "member_removed"}
        assert removal_coherence.event == "initiative.coherence_updated"
    finally:
        events.canvas_channel.unsubscribe(subscriber)


async def test_membership_event_is_published_when_scoring_is_unavailable(client, db_session, typesafe):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Wohnen")
    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 1", "Mehr wohnen")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 2", "Mehr wohnen")
    await _add_member(client, initiative_id, c1, headers)
    typesafe.unavailable = True

    subscriber = events.canvas_channel.subscribe()
    try:
        await _add_member(client, initiative_id, c2, headers)
        change = subscriber.get_nowait()
        assert change.event == "initiative.updated"
        assert change.data == {"initiative_id": initiative_id, "change": "member_added"}
        assert subscriber.empty()
    finally:
        events.canvas_channel.unsubscribe(subscriber)


async def test_domain_and_narrative_similarity_are_independent(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Mobilisierung")

    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen", "Menschen mobilisieren")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Verkehr", "Menschen mobilisieren")
    await _add_member(client, initiative_id, c1, headers)
    await _add_member(client, initiative_id, c2, headers)

    detail = await client.get(f"/initiatives/{initiative_id}", headers=headers)

    # The topics differ, but both campaigns have the same goal/narrative.
    assert detail.text.count('text-3xl font-black text-brand-cyan">0.00</p>') == 1
    assert detail.text.count('text-3xl font-black text-brand-cyan">1.00</p>') == 1


async def test_outlier_none_clear_marks_no_campaign(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Gemischt")

    for thema in ("Wohnen", "Verkehr", "Mobilisieren"):
        campaign_id = await _create_campaign(client, str(berlin.id), headers, thema, thema)
        await _add_member(client, initiative_id, campaign_id, headers)

    detail = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Ausreißer-Kandidat</span>" not in detail.text
    initiative = await db_session.get(Initiative, uuid.UUID(initiative_id))
    await db_session.refresh(initiative)
    assert initiative.outlier_campaign_id is None


async def test_coherence_score_none_with_fewer_than_two_scorable_members(client, db_session, typesafe):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Solo")
    c1 = await _create_campaign(client, str(berlin.id), headers, "Thema", "Ziel")
    await _add_member(client, initiative_id, c1, headers)

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Noch nicht berechenbar" in resp.text
    assert typesafe.calls == []


async def test_remove_member_recomputes_coherence(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Bauen und Wohnen")
    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 1", "Ziel")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 2", "Ziel")
    await _add_member(client, initiative_id, c1, headers)
    await _add_member(client, initiative_id, c2, headers)

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Noch nicht berechenbar" not in resp.text

    resp = await client.post(f"/initiatives/{initiative_id}/members/{c2}/remove", headers=headers)
    assert resp.status_code == 303

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Noch nicht berechenbar" in resp.text  # back to a single member -> scores are unavailable again


async def test_unavailable_typesafe_keeps_previous_scores(client, db_session, typesafe):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Bauen und Wohnen")
    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 1", "Mehr wohnen")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 2", "Mehr wohnen")
    await _add_member(client, initiative_id, c1, headers)
    await _add_member(client, initiative_id, c2, headers)

    typesafe.unavailable = True
    c3 = await _create_campaign(client, str(berlin.id), headers, "Verkehr 3", "Weniger Autos")
    await _add_member(client, initiative_id, c3, headers)

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert resp.text.count('text-3xl font-black text-brand-cyan">1.00</p>') == 2


async def test_campaign_edit_and_initiative_edit_trigger_rescoring(client, db_session, typesafe):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Wohnen", "Alt")
    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 1", "Mehr wohnen")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 2", "Mehr wohnen")
    await _add_member(client, initiative_id, c1, headers)
    await _add_member(client, initiative_id, c2, headers)
    typesafe.calls.clear()

    await client.post(f"/campaigns/{c1}/fields", data={"thema": "Verkehr 1"}, headers=headers)
    assert len(typesafe.calls) == 1

    # Fields outside Thema, Ziel and Storytelling never reach TypeSafe.
    await client.post(f"/campaigns/{c1}/fields", data={"zielgruppen": "Mieter:innen"}, headers=headers)
    assert len(typesafe.calls) == 1

    await client.post(
        f"/initiatives/{initiative_id}/edit", data={"name": "Wohnen", "description": "Neu"}, headers=headers
    )
    assert len(typesafe.calls) == 2
    assert typesafe.calls[-1]["state"]["initiative"]["description"] == "Neu"

    await client.post(
        f"/initiatives/{initiative_id}/edit", data={"name": "Wohnen", "description": "Neu"}, headers=headers
    )
    assert len(typesafe.calls) == 2


async def test_deleting_outlier_campaign_clears_outlier(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    initiative_id = await _create_initiative(client, str(berlin.id), headers, "Bauen und Wohnen")
    campaign_ids = [
        await _create_campaign(client, str(berlin.id), headers, thema, "Ziel")
        for thema in ("Wohnen 1", "Wohnen 2", "Verkehr 3")
    ]
    for campaign_id in campaign_ids:
        await _add_member(client, initiative_id, campaign_id, headers)

    initiative = await db_session.get(Initiative, uuid.UUID(initiative_id))
    await db_session.refresh(initiative)
    assert initiative.outlier_campaign_id == uuid.UUID(campaign_ids[2])

    await db_session.execute(delete(Campaign).where(Campaign.id == uuid.UUID(campaign_ids[2])))
    await db_session.commit()
    await db_session.refresh(initiative)
    assert initiative.outlier_campaign_id is None
