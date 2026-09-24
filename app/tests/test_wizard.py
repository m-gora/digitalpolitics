import pytest

from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


async def test_creation_starts_at_district_selection_then_goal_definition(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})

    response = await client.get("/campaigns/new", headers=headers)
    assert response.status_code == 200
    assert "Wo findet die Kampagne statt?" in response.text
    assert "Wähle die Gliederung" in response.text

    response = await client.post("/campaigns/new", data={"district_id": str(berlin.id)}, headers=headers)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.endswith("/wizard/zieldefinition")

    response = await client.get(location, headers=headers)
    assert response.status_code == 200
    assert "Schritt 2 von 4" in response.text
    assert "Zieldefinition" in response.text
    assert "Worum geht es?" in response.text
    assert "Was ist das Ziel (politisch und kommunikativ)?" in response.text


async def test_goal_definition_must_be_complete_before_audience_step_unlocks(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    response = await client.post("/campaigns/new", data={"district_id": str(berlin.id)}, headers=headers)
    campaign_id = response.headers["location"].split("/")[2]

    response = await client.get(f"/campaigns/{campaign_id}/wizard/zielgruppen-kanaele", headers=headers)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/wizard/zieldefinition")

    response = await client.post(
        f"/campaigns/{campaign_id}/wizard/zieldefinition",
        data={"thema": "", "ziel": "", "action": "next"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Bitte fülle alle Felder dieses Schritts aus" in response.text

    response = await client.post(
        f"/campaigns/{campaign_id}/wizard/zieldefinition",
        data={"thema": "Wohnraum", "ziel": "Mehr bezahlbarer Wohnraum", "action": "next"},
        headers=headers,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/wizard/zielgruppen-kanaele")


async def test_audience_and_execution_steps_show_explanations_and_progress_sequentially(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    response = await client.post("/campaigns/new", data={"district_id": str(berlin.id)}, headers=headers)
    campaign_id = response.headers["location"].split("/")[2]

    await client.post(
        f"/campaigns/{campaign_id}/wizard/zieldefinition",
        data={"thema": "Wohnen", "ziel": "Mehr Wohnraum", "action": "next"},
        headers=headers,
    )
    response = await client.get(f"/campaigns/{campaign_id}/wizard/zielgruppen-kanaele", headers=headers)
    assert "Zielgruppen &amp; Kanäle" in response.text
    assert "Gibt es spezielle Zielgruppen?" in response.text
    assert "Welche Zulieferer brauchen wir? Wo erreichen wir die Zielgruppe?" in response.text
    assert "Welche Multiplikatoren haben wir in unserem Umfeld?" in response.text

    response = await client.get(f"/campaigns/{campaign_id}/wizard/material-organisation-storytelling", headers=headers)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/wizard/zielgruppen-kanaele")

    response = await client.post(
        f"/campaigns/{campaign_id}/wizard/zielgruppen-kanaele",
        data={
            "zielgruppen": "Mieter:innen",
            "kanaele": "Infostände",
            "momentum": "Mieterverein",
            "motiv": "Gerechtigkeit",
            "action": "next",
        },
        headers=headers,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/wizard/material-organisation-storytelling")

    response = await client.get(f"/campaigns/{campaign_id}/wizard/material-organisation-storytelling", headers=headers)
    assert "Material, Organisation &amp; Storytelling" in response.text
    assert "Was sollte man den Aktivisten zur Verfügung stellen?" in response.text
    assert "Welche Daten unserer Zielgruppe wären besonders nützlich" in response.text
    assert "Wie startet die Aktion um erfolgreich Aufmerksamkeit zu erzeugen?" in response.text


async def test_wizard_requires_campaign_district_write_access(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    outsider = auth_headers("outsider", set())
    response = await client.post("/campaigns/new", data={"district_id": str(berlin.id)}, headers=outsider)
    assert response.status_code == 403


async def test_campaign_overview_links_to_wizard_and_shows_field_explanations(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    response = await client.post("/campaigns", data={"district_id": str(berlin.id)}, headers=headers)
    campaign_id = response.headers["location"].split("/")[2]

    response = await client.get(f"/campaigns/{campaign_id}", headers=headers)
    assert f"/campaigns/{campaign_id}/wizard/zieldefinition" in response.text
    assert "Zieldefinition" in response.text
    assert "Zielgruppen &amp; Kanäle" in response.text
    assert "Material, Organisation &amp; Storytelling" in response.text
    assert "Worum geht es?" in response.text
    assert 'src="/static/js/htmx.min.js"' in response.text
    assert 'id="request-indicator"' in response.text

    asset_response = await client.get("/static/js/htmx.min.js")
    assert asset_response.status_code == 200
    assert len(asset_response.content) > 10_000
