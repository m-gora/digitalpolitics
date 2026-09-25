from types import SimpleNamespace
from typing import Any, cast

import pytest

from dpp.ai import GoogleGenAIProvider

pytestmark = pytest.mark.asyncio


class FakeGoogleModels:
    def __init__(self):
        self.embed_request = None
        self.generate_request = None

    async def embed_content(self, **kwargs):
        self.embed_request = kwargs
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])])

    async def generate_content(self, **kwargs):
        self.generate_request = kwargs
        return SimpleNamespace(text="  Zusammenfassung  ")


async def test_google_embeddings_use_symmetric_sentence_similarity_prefix_and_1536_dimensions():
    provider = GoogleGenAIProvider(
        api_key="test-key",
        embedding_model="gemini-embedding-2",
        text_model="gemini-3.5-flash-lite",
    )
    fake_models = FakeGoogleModels()
    cast(Any, provider).client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))

    vector = await provider.embed("Thema: bezahlbares Wohnen")

    assert vector == [0.1, 0.2]
    assert fake_models.embed_request is not None
    assert fake_models.embed_request["contents"] == (
        "task: sentence similarity | query: Thema: bezahlbares Wohnen"
    )
    assert fake_models.embed_request["config"].output_dimensionality == 1536


async def test_google_provider_generates_text_through_async_client():
    provider = GoogleGenAIProvider(
        api_key="test-key",
        embedding_model="gemini-embedding-2",
        text_model="gemini-3.5-flash-lite",
    )
    fake_models = FakeGoogleModels()
    cast(Any, provider).client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))

    text = await provider.generate_text("Fasse die Kampagne zusammen")

    assert text == "Zusammenfassung"
    assert fake_models.generate_request is not None
    assert fake_models.generate_request["model"] == "gemini-3.5-flash-lite"
    assert fake_models.generate_request["contents"] == "Fasse die Kampagne zusammen"
    assert fake_models.generate_request["config"].automatic_function_calling.disable is True
