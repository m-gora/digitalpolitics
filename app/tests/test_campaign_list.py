import pytest

from dpp.campaign.models import Campaign, CampaignStatus
from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


async def _add_campaign(session, district, *, status, thema, **fields) -> Campaign:
    campaign = Campaign(district_id=district.id, status=status, thema=thema, **fields)
    session.add(campaign)
    await session.commit()
    return campaign


async def test_campaign_list_defaults_to_running_and_can_filter_status(
    client, db_session
):
    district = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(district.id)})
    await _add_campaign(
        db_session,
        district,
        status=CampaignStatus.RUNNING,
        thema="Laufende Verkehrswende",
    )
    await _add_campaign(
        db_session,
        district,
        status=CampaignStatus.DRAFT,
        thema="Entwurf für mehr Radwege",
    )
    await _add_campaign(
        db_session,
        district,
        status=CampaignStatus.FINISHED,
        thema="Abgeschlossene Schulhofkampagne",
    )

    response = await client.get("/campaigns", headers=headers)

    assert response.status_code == 200
    assert "Laufende Verkehrswende" in response.text
    assert "Entwurf für mehr Radwege" not in response.text
    assert "Abgeschlossene Schulhofkampagne" not in response.text
    assert 'name="status"' in response.text
    assert '<option value="running" selected>' in response.text

    response = await client.get("/campaigns?status=finished", headers=headers)
    assert "Abgeschlossene Schulhofkampagne" in response.text
    assert "Laufende Verkehrswende" not in response.text

    response = await client.get("/campaigns?status=all", headers=headers)
    assert "Laufende Verkehrswende" in response.text
    assert "Entwurf für mehr Radwege" in response.text
    assert "Abgeschlossene Schulhofkampagne" in response.text


async def test_campaign_list_searches_campaign_fields_summary_and_district(
    client, db_session
):
    district = await make_district(db_session, "Gliederung Sonnental")
    headers = auth_headers("anna", {str(district.id)})
    await _add_campaign(
        db_session,
        district,
        status=CampaignStatus.RUNNING,
        thema="Nahverkehr verbessern",
        ziel="Barrierefreie Haltestellen",
        ai_summary="Der Fahrgastbeirat macht den ÖPNV zugänglicher.",
    )

    answer_match = await client.get("/campaigns?q=Haltestellen", headers=headers)
    summary_match = await client.get("/campaigns?q=Fahrgastbeirat", headers=headers)
    district_match = await client.get("/campaigns?q=Sonnental", headers=headers)

    assert "Nahverkehr verbessern" in answer_match.text
    assert "Nahverkehr verbessern" in summary_match.text
    assert "Nahverkehr verbessern" in district_match.text


async def test_campaign_list_shows_no_match_state_and_rejects_unknown_status(
    client, db_session
):
    district = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(district.id)})
    await _add_campaign(
        db_session,
        district,
        status=CampaignStatus.RUNNING,
        thema="Klimaschutz",
    )

    response = await client.get("/campaigns?q=unbekannteswort", headers=headers)

    assert response.status_code == 200
    assert (
        "Keine Kampagnen entsprechen deiner Suche und Statusauswahl." in response.text
    )
    assert "Noch keine Kampagnen angelegt." not in response.text

    invalid_status = await client.get("/campaigns?status=unknown", headers=headers)
    assert invalid_status.status_code == 422


async def test_campaign_list_distinguishes_empty_campaign_table(client):
    response = await client.get("/campaigns", headers=auth_headers("anna", set()))

    assert response.status_code == 200
    assert "Noch keine Kampagnen angelegt." in response.text
    assert (
        "Keine Kampagnen entsprechen deiner Suche und Statusauswahl."
        not in response.text
    )
