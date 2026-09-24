import pytest

import dpp.campaign.coherence as coherence_module
from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio

EMBEDDING_DIM = 1536
KEYWORDS = ["wohnen", "verkehr"]


def _fake_vector(text: str) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    lower = (text or "").lower()
    for i, kw in enumerate(KEYWORDS):
        if kw in lower:
            vec[i] = 1.0
    return vec


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


async def test_initiative_rejects_cross_district_campaign(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=berlin)
    headers = auth_headers("anna", {str(berlin.id), str(kreuzberg.id)})

    resp = await client.post(
        "/initiatives", data={"district_id": str(berlin.id), "name": "Bauen und Wohnen"}, headers=headers
    )
    initiative_id = resp.headers["location"].rsplit("/", 1)[-1]

    other_district_campaign = await _create_campaign(client, str(kreuzberg.id), headers, "Wohnen A", "Ziel A")

    resp = await client.post(
        f"/initiatives/{initiative_id}/members",
        data={"campaign_id": other_district_campaign},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_coherence_score_reflects_narrative_similarity(client, db_session):
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
    assert "100%" in resp.text  # identical narrative keywords -> cosine similarity 1.0

    # A third, thematically unrelated campaign lowers the average coherence.
    c3 = await _create_campaign(client, str(berlin.id), headers, "Verkehr Kampagne", "Weniger Autos im Kiez")
    resp = await client.post(f"/initiatives/{initiative_id}/members", data={"campaign_id": c3}, headers=headers)
    assert resp.status_code == 303

    resp = await client.get(f"/initiatives/{initiative_id}", headers=headers)
    assert "100%" not in resp.text


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
