import pytest

from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


async def _create_campaign(client, district_id: str, headers: dict) -> str:
    resp = await client.post("/campaigns", data={"district_id": district_id}, headers=headers)
    assert resp.status_code == 303
    return resp.headers["location"].rsplit("/", 1)[-1]


async def test_core_gate_blocks_layer1(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    campaign_id = await _create_campaign(client, str(berlin.id), headers)

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"zielgruppen": "x"}, headers=headers)
    assert resp.status_code == 400

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"thema": "Thema"}, headers=headers)
    assert resp.status_code == 303

    # Still incomplete (missing ziel) -> layer1 still locked
    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"zielgruppen": "x"}, headers=headers)
    assert resp.status_code == 400

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"ziel": "Ziel"}, headers=headers)
    assert resp.status_code == 303

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"zielgruppen": "x"}, headers=headers)
    assert resp.status_code == 303


async def test_layer1_gate_blocks_layer2(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    campaign_id = await _create_campaign(client, str(berlin.id), headers)

    await client.post(f"/campaigns/{campaign_id}/fields", data={"thema": "T", "ziel": "Z"}, headers=headers)

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"service": "x"}, headers=headers)
    assert resp.status_code == 400

    await client.post(
        f"/campaigns/{campaign_id}/fields",
        data={"zielgruppen": "a", "kanaele": "b", "momentum": "c", "motiv": "d"},
        headers=headers,
    )

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"service": "x"}, headers=headers)
    assert resp.status_code == 303


async def test_fields_not_editable_outside_draft(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    campaign_id = await _create_campaign(client, str(berlin.id), headers)

    await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": "review"}, headers=headers)

    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"thema": "later"}, headers=headers)
    assert resp.status_code == 400


async def test_full_lifecycle_and_retro_auto_creation(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    campaign_id = await _create_campaign(client, str(berlin.id), headers)

    # No retro yet
    resp = await client.get(f"/campaigns/{campaign_id}/retrospective", headers=headers)
    assert "Noch keine Retrospektive" in resp.text

    for to_status in ("review", "running", "finished"):
        resp = await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": to_status}, headers=headers)
        assert resp.status_code == 303, to_status

    resp = await client.get(f"/campaigns/{campaign_id}/retrospective", headers=headers)
    assert "Zielerreichung" in resp.text

    # Invalid transition: Finished -> Running
    resp = await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": "running"}, headers=headers)
    assert resp.status_code == 400

    # Valid: Finished -> Archived
    resp = await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": "archived"}, headers=headers)
    assert resp.status_code == 303


async def test_review_can_go_back_to_draft(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    campaign_id = await _create_campaign(client, str(berlin.id), headers)

    await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": "review"}, headers=headers)
    resp = await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": "draft"}, headers=headers)
    assert resp.status_code == 303

    # Editable again
    resp = await client.post(f"/campaigns/{campaign_id}/fields", data={"thema": "back to draft"}, headers=headers)
    assert resp.status_code == 303


async def test_aborted_also_gets_retro(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    campaign_id = await _create_campaign(client, str(berlin.id), headers)

    for to_status in ("review", "running", "aborted"):
        resp = await client.post(f"/campaigns/{campaign_id}/transition", data={"to_status": to_status}, headers=headers)
        assert resp.status_code == 303, to_status

    resp = await client.get(f"/campaigns/{campaign_id}/retrospective", headers=headers)
    assert "Zielerreichung" in resp.text
