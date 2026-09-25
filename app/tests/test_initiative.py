import uuid

import pytest

import dpp.campaign.coherence as coherence_module
from dpp.campaign.models import Campaign
from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio

EMBEDDING_DIM = 1536
KEYWORDS = ["wohnen", "verkehr", "mobilisieren"]


def _fake_vector(text: str) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    lower = (text or "").lower()
    for i, kw in enumerate(KEYWORDS):
        if kw in lower:
            vec[i] = 1.0
    return vec


async def test_similarity_texts_exclude_operational_fields():
    campaign = Campaign(
        district_id=uuid.uuid4(),
        thema="Bezahlbares Wohnen",
        ziel="Mehr Wohnungen schaffen",
        storytelling="Stimmen aus dem Kiez",
        zielgruppen="Mieter:innen",
        kanaele="Infostände",
        tools="Kontaktformular",
        phasen_flow="Infostand, Auswertung, Kampagnenstart",
    )

    assert coherence_module.domain_text(campaign) == "Bezahlbares Wohnen"
    narrative = coherence_module.narrative_text(campaign)
    assert narrative == "Ziel: Mehr Wohnungen schaffen\nStorytelling: Stimmen aus dem Kiez"
    assert "Mieter:innen" not in narrative
    assert "Infostände" not in narrative
    assert "Kontaktformular" not in narrative
    assert "Kampagnenstart" not in narrative


@pytest.fixture(autouse=True)
def _mock_embeddings(monkeypatch):
    async def fake_embed_text(text: str):
        return _fake_vector(text)

    monkeypatch.setattr(coherence_module, "embed_text", fake_embed_text)


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


async def test_initiative_shows_separate_domain_and_narrative_scores(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(berlin.id), "name": "Bauen und Wohnen"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]

    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen Kampagne 1", "Mehr wohnen schaffen")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen Kampagne 2", "Auch mehr wohnen schaffen")

    await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c1}, headers=headers)
    resp = await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c2}, headers=headers)
    assert resp.status_code == 303

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert resp.text.count('text-3xl font-black text-brand-cyan">1.00</p>') == 2

    # A third, thematically unrelated campaign lowers the average coherence.
    c3 = await _create_campaign(client, str(berlin.id), headers, "Verkehr Kampagne", "Weniger Autos im Kiez")
    resp = await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c3}, headers=headers)
    assert resp.status_code == 303

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert resp.text.count('text-3xl font-black text-brand-cyan">0.33</p>') == 2
    assert "Domain-Ausreißer" in resp.text
    assert "Narrativ-Ausreißer" in resp.text
    assert resp.text.count("Kampagnen in dieser Initiative") == 1
    assert "Domain: 0.00" in resp.text
    assert "Narrativ: 0.00" in resp.text
    assert "aus Initiative entfernen" in resp.text


async def test_domain_and_narrative_similarity_are_independent(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(berlin.id), "name": "Mobilisierung"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]

    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen", "Menschen mobilisieren")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Verkehr", "Menschen mobilisieren")
    await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c1}, headers=headers)
    await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c2}, headers=headers)

    detail = await client.get(f"/initiatives/{initiative_id}", headers=headers)

    # The topics differ, but both campaigns have the same goal/narrative.
    assert 'text-3xl font-black text-brand-cyan">0.00</p>' in detail.text
    assert 'text-3xl font-black text-brand-cyan">1.00</p>' in detail.text
    assert "Domain: 0.00" in detail.text
    assert "Narrativ: 1.00" in detail.text


async def test_coherence_score_none_with_fewer_than_two_embedded_members(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(berlin.id), "name": "Solo"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]
    c1 = await _create_campaign(client, str(berlin.id), headers, "Thema", "Ziel")

    resp = await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c1}, headers=headers)
    assert resp.status_code == 303

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Noch nicht berechenbar" in resp.text


async def test_remove_member_recomputes_coherence(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(berlin.id), "name": "Bauen und Wohnen"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]
    c1 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 1", "Ziel")
    c2 = await _create_campaign(client, str(berlin.id), headers, "Wohnen 2", "Ziel")

    await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c1}, headers=headers)
    await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c2}, headers=headers)

    resp = await client.post(f"/initiatives/{initiative_id}/members/{c2}/remove", headers=headers)
    assert resp.status_code == 303

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "Noch nicht berechenbar" in resp.text  # back to a single member -> score is None again
