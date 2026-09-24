import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


async def test_landing_requires_authentication(client):
    response = await client.get("/", headers={"Accept": "text/html"})

    assert response.status_code == 401
    assert "Anmeldung erforderlich" in response.text


async def test_landing_shows_available_and_coming_soon_modules(client):
    response = await client.get("/", headers=auth_headers("anna", set()))

    assert response.status_code == 200
    assert 'href="/campaigns"' in response.text
    assert "Kampagnen" in response.text
    assert "Infostand" in response.text
    assert "Crowdsourcing" in response.text
    assert "Unterstützungsunterschriften" in response.text
    assert "Beschlussexplorer" in response.text
    assert "Im Einsatz – wird integriert" in response.text
    assert "Integration in Arbeit" in response.text
    assert "Stimmungsbilder und Ideen von Bürger:innen" in response.text
    assert "Bald verfügbar" in response.text
    assert 'href="/infostand"' not in response.text
    assert 'href="/crowdsourcing"' not in response.text
    assert 'href="/petitions"' not in response.text
    assert 'href="/beschlussexplorer"' not in response.text
    assert 'viewBox="0 0 178.08 69.73"' in response.text
    assert '<link rel="icon" type="image/svg+xml" href="/static/img/fdp-logo.svg"' in response.text
    assert "module-carousel flex snap-x snap-mandatory" in response.text
    assert "w-[85%] shrink-0 snap-center" in response.text
    assert "sm:grid sm:grid-cols-3" in response.text
    assert "module-card-title min-h-14" in response.text
    assert response.text.index(">Kampagnen</h2>") < response.text.index(">Infostand</h2>")
    assert response.text.index(">Infostand</h2>") < response.text.index(">Crowdsourcing</h2>")
    assert response.text.index(">Crowdsourcing</h2>") < response.text.index(">Unterstützungsunterschriften</h2>")
    assert response.text.index(">Unterstützungsunterschriften</h2>") < response.text.index(">Beschlussexplorer</h2>")

    logo_response = await client.get("/static/img/fdp-logo.svg")
    assert logo_response.status_code == 200
    assert "viewBox=\"0 0 178.08 69.73\"" in logo_response.text
