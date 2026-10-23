import uuid
from types import SimpleNamespace

import pytest

import dpp.campaign.coherence as coherence_module
from dpp.campaign.coherence import CoherenceResult, score_initiative
from dpp.campaign.models import Campaign, Initiative

pytestmark = pytest.mark.asyncio


def make_campaign(thema: str | None = "Wohnen", ziel: str | None = "Mehr Wohnraum", **kwargs) -> Campaign:
    return Campaign(id=uuid.uuid4(), district_id=uuid.uuid4(), thema=thema, ziel=ziel, **kwargs)


def make_initiative() -> Initiative:
    return Initiative(id=uuid.uuid4(), name="Wohnen", description="Gemeinsame Botschaft")


class Recorder:
    def __init__(self, domain=3.0, narrative=2.0, outlier=None):
        self.calls: list[tuple[dict, dict]] = []
        self.domain = domain
        self.narrative = narrative
        self.outlier = outlier

    async def __call__(self, state, questions):
        self.calls.append((state, questions))
        scores = {
            "domain_similarity": SimpleNamespace(score=self.domain),
            "narrative_similarity": SimpleNamespace(score=self.narrative),
        }
        choices = {"initiative_outlier": SimpleNamespace(choice=self.outlier or "none_clear")}
        return SimpleNamespace(scores=scores, choices=choices)


async def test_scores_are_normalized_to_unit_interval(monkeypatch):
    recorder = Recorder(domain=3.0, narrative=2.0)
    monkeypatch.setattr(coherence_module, "_ask_typesafe", recorder)

    result = await score_initiative(make_initiative(), [make_campaign(), make_campaign()])

    assert result == CoherenceResult(domain_score=0.75, narrative_score=0.5, outlier_campaign_id=None)
    assert set(recorder.calls[0][1]) == {"domain_similarity", "narrative_similarity"}


async def test_out_of_range_scores_are_clamped(monkeypatch):
    monkeypatch.setattr(coherence_module, "_ask_typesafe", Recorder(domain=7.0, narrative=-1.0))

    result = await score_initiative(make_initiative(), [make_campaign(), make_campaign()])

    assert result is not None
    assert (result.domain_score, result.narrative_score) == (1.0, 0.0)


async def test_state_labels_campaigns_without_internal_ids(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(coherence_module, "_ask_typesafe", recorder)
    campaigns = [make_campaign(data_harvest="secret"), make_campaign(tools="Kontaktformular")]

    await score_initiative(make_initiative(), campaigns)

    state = recorder.calls[0][0]
    assert [c["id"] for c in state["campaigns"]] == ["C1", "C2"]
    assert all(set(c) == {"id", "thema", "ziel", "storytelling"} for c in state["campaigns"])
    flattened = str(state)
    assert "secret" not in flattened
    assert "Kontaktformular" not in flattened
    assert not any(str(campaign.id) in flattened for campaign in campaigns)


async def test_fewer_than_two_campaigns_is_unavailable_without_request(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(coherence_module, "_ask_typesafe", recorder)

    result = await score_initiative(make_initiative(), [make_campaign()])

    assert result == CoherenceResult()
    assert recorder.calls == []


async def test_only_dimensions_with_two_campaigns_are_asked(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(coherence_module, "_ask_typesafe", recorder)
    campaigns = [make_campaign(ziel=None), make_campaign(ziel="  ")]

    result = await score_initiative(make_initiative(), campaigns)

    assert set(recorder.calls[0][1]) == {"domain_similarity"}
    assert result is not None
    assert result.domain_score == 0.75
    assert result.narrative_score is None


async def test_outlier_needs_three_campaigns_and_maps_label_to_campaign(monkeypatch):
    recorder = Recorder(outlier="C2")
    monkeypatch.setattr(coherence_module, "_ask_typesafe", recorder)
    campaigns = [make_campaign(), make_campaign()]

    result = await score_initiative(make_initiative(), campaigns)
    assert "initiative_outlier" not in recorder.calls[0][1]
    assert result is not None
    assert result.outlier_campaign_id is None

    campaigns.append(make_campaign())
    result = await score_initiative(make_initiative(), campaigns)
    questions = recorder.calls[1][1]
    assert set(questions["initiative_outlier"].criteria) == {"C1", "C2", "C3", "none_clear"}
    ordered = sorted(campaigns, key=lambda campaign: str(campaign.id))
    assert result is not None
    assert result.outlier_campaign_id == ordered[1].id


async def test_unknown_outlier_label_is_ignored(monkeypatch):
    monkeypatch.setattr(coherence_module, "_ask_typesafe", Recorder(outlier="C99"))

    result = await score_initiative(make_initiative(), [make_campaign() for _ in range(3)])

    assert result is not None
    assert result.outlier_campaign_id is None


async def test_missing_api_key_returns_none():
    result = await score_initiative(make_initiative(), [make_campaign(), make_campaign()])

    assert result is None


async def test_client_error_returns_none(monkeypatch):
    class FailingClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def system_one(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(coherence_module, "AsyncTypeSafeClient", FailingClient)
    monkeypatch.setattr(
        coherence_module, "get_settings", lambda: SimpleNamespace(typesafe_api_key="key", typesafe_model="m")
    )

    result = await score_initiative(make_initiative(), [make_campaign(), make_campaign()])

    assert result is None


async def test_malformed_response_returns_none(monkeypatch):
    async def malformed(state, questions):
        return SimpleNamespace(scores={}, choices={})

    monkeypatch.setattr(coherence_module, "_ask_typesafe", malformed)

    result = await score_initiative(make_initiative(), [make_campaign(), make_campaign()])

    assert result is None
