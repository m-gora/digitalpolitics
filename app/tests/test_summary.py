import uuid

import pytest

import dpp.campaign.coherence as coherence_module
import dpp.campaign.router as campaign_router
import dpp.campaign.summary as summary_module
from dpp.campaign.models import Campaign, CampaignStatus
from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


def complete_campaign(**overrides) -> Campaign:
    values = {
        "status": CampaignStatus.DRAFT,
        "thema": "Bezahlbares Wohnen",
        "ziel": "Mehr bezahlbare Wohnungen",
        "zielgruppen": "Mieter:innen",
        "kanaele": "Infostände",
        "momentum": "Lokale Initiativen",
        "motiv": "Wohnen muss bezahlbar bleiben",
        "service": "Beratung anbieten",
        "data_harvest": "NEVER INCLUDE THIS CITIZEN DATA PLAN",
        "tools": "Kontaktformular",
        "phasen_flow": "Infostand, Auswertung, Kampagnenstart",
        "storytelling": "Stimmen aus dem Kiez",
    }
    values.update(overrides)
    return Campaign(**values)


class FakeAIProvider:
    def __init__(self, response: str | None = None):
        self.prompts: list[str] = []
        self.response = response

    async def embed(self, text: str) -> list[float] | None:
        return [0.0] * 1536

    async def generate_text(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return self.response or f"Kurzzusammenfassung {len(self.prompts)}"


async def test_summary_prompt_includes_canvas_context_but_excludes_data_harvest():
    campaign = complete_campaign()

    prompt = summary_module.build_summary_prompt(campaign)

    assert "Bezahlbares Wohnen" in prompt
    assert "Infostände" in prompt
    assert "Stimmen aus dem Kiez" in prompt
    assert "Data Harvest" not in prompt
    assert "NEVER INCLUDE THIS CITIZEN DATA PLAN" not in prompt
    assert "vollständigen Satz" in prompt
    assert "höchstens 20 Wörtern" in prompt
    assert "keine Auslassungspunkte" in prompt


async def test_generated_summary_is_stored_without_mid_sentence_truncation(monkeypatch):
    complete_response = "Diese Kampagne bündelt Ziele und Maßnahmen. " + "Wichtiger Ansatz bleibt dokumentiert " * 8 + "."
    provider = FakeAIProvider(response=complete_response)
    monkeypatch.setattr(summary_module, "get_ai_provider", lambda: provider)
    campaign = complete_campaign()

    assert await summary_module.update_campaign_summary(campaign) is True
    assert campaign.ai_summary is not None
    assert campaign.ai_summary == complete_response
    assert not campaign.ai_summary.endswith("…")


async def test_summary_only_generates_for_a_complete_canvas(monkeypatch):
    provider = FakeAIProvider()
    monkeypatch.setattr(summary_module, "get_ai_provider", lambda: provider)
    campaign = complete_campaign(storytelling=None)

    assert not campaign.execution_complete
    assert not campaign.canvas_complete
    assert await summary_module.update_campaign_summary(campaign) is False
    assert provider.prompts == []

    campaign.storytelling = "Stimmen aus dem Kiez"
    assert campaign.execution_complete
    assert campaign.canvas_complete
    assert await summary_module.update_campaign_summary(campaign) is True
    assert campaign.ai_summary == "Kurzzusammenfassung 1"
    assert campaign.ai_summary_generated_at is not None
    assert "NEVER INCLUDE THIS CITIZEN DATA PLAN" not in provider.prompts[0]


async def test_completed_canvas_edits_regenerate_summary_and_list_displays_it(
    client, db_session, monkeypatch
):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    provider = FakeAIProvider()
    monkeypatch.setattr(summary_module, "get_ai_provider", lambda: provider)

    async def fake_embed_text(text: str) -> list[float]:
        return [0.0] * 1536

    monkeypatch.setattr(coherence_module, "embed_text", fake_embed_text)

    response = await client.post("/campaigns", data={"district_id": str(berlin.id)}, headers=headers)
    campaign_id = response.headers["location"].rsplit("/", 1)[-1]

    # An incomplete canvas is saved, but does not trigger a summary.
    response = await client.post(
        f"/campaigns/{campaign_id}/fields",
        data={"thema": "Bezahlbares Wohnen", "ziel": "Mehr bezahlbare Wohnungen"},
        headers=headers,
    )
    assert response.status_code == 303
    assert provider.prompts == []

    fields = {
        "zielgruppen": "Mieter:innen",
        "kanaele": "Infostände",
        "momentum": "Lokale Initiativen",
        "motiv": "Wohnen muss bezahlbar bleiben",
        "service": "Beratung anbieten",
        "data_harvest": "NEVER INCLUDE THIS CITIZEN DATA PLAN",
        "tools": "Kontaktformular",
        "phasen_flow": "Infostand, Auswertung, Kampagnenstart",
        "storytelling": "Stimmen aus dem Kiez",
    }
    response = await client.post(f"/campaigns/{campaign_id}/fields", data=fields, headers=headers)
    assert response.status_code == 303
    assert len(provider.prompts) == 1
    assert "NEVER INCLUDE THIS CITIZEN DATA PLAN" not in provider.prompts[0]

    # A subsequent edit to a complete canvas regenerates its summary.
    response = await client.post(
        f"/campaigns/{campaign_id}/fields", data={"motiv": "Gemeinsam den Kiez gestalten"}, headers=headers
    )
    assert response.status_code == 303
    assert len(provider.prompts) == 2

    list_response = await client.get("/campaigns", headers=headers)
    assert list_response.status_code == 200
    assert "Kurzzusammenfassung 2" in list_response.text
    assert 'data-campaign-list="true"' in list_response.text
    assert '"campaign.summary_updated"' in list_response.text


async def test_missing_embedding_retries_after_non_narrative_field_edit(client, db_session, monkeypatch):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("anna", {str(berlin.id)})
    embedding_attempts = []

    async def record_embedding_attempt(campaign_id):
        embedding_attempts.append(campaign_id)

    monkeypatch.setattr(campaign_router, "_recompute_embedding_and_coherence", record_embedding_attempt)

    response = await client.post("/campaigns", data={"district_id": str(berlin.id)}, headers=headers)
    campaign_id = response.headers["location"].rsplit("/", 1)[-1]
    await client.post(
        f"/campaigns/{campaign_id}/fields",
        data={"thema": "Wohnen", "ziel": "Mehr Wohnraum"},
        headers=headers,
    )
    assert embedding_attempts == [uuid.UUID(campaign_id)]

    await client.post(
        f"/campaigns/{campaign_id}/fields", data={"zielgruppen": "Mieter:innen"}, headers=headers
    )
    assert embedding_attempts == [uuid.UUID(campaign_id), uuid.UUID(campaign_id)]
