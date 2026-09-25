"""Provider-neutral AI interface for embeddings and text generation."""

import logging
from functools import lru_cache
from typing import Protocol

from openai import AsyncOpenAI

from dpp.config import get_settings

logger = logging.getLogger(__name__)


class AIProvider(Protocol):
    async def embed(self, text: str) -> list[float] | None: ...

    async def generate_text(self, prompt: str) -> str | None: ...


class OpenAIProvider:
    def __init__(self, api_key: str, embedding_model: str, text_model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.embedding_model = embedding_model
        self.text_model = text_model

    async def embed(self, text: str) -> list[float] | None:
        response = await self.client.embeddings.create(model=self.embedding_model, input=text)
        if not response.data:
            return None
        return response.data[0].embedding

    async def generate_text(self, prompt: str) -> str | None:
        response = await self.client.chat.completions.create(
            model=self.text_model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=100,
            temperature=0.2,
        )
        if not response.choices:
            return None
        content = response.choices[0].message.content
        return content.strip() if content else None


class GoogleGenAIProvider:
    """Google GenAI adapter.

    Campaign domain and narrative similarity use symmetric sentence-similarity
    embeddings. The same task prefix is applied to every input so all stored
    vectors are comparable for this task.
    """

    EMBEDDING_DIMENSIONS = 1536

    def __init__(self, api_key: str, embedding_model: str, text_model: str) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.embedding_model = embedding_model
        self.text_model = text_model

    async def embed(self, text: str) -> list[float] | None:
        from google.genai import types

        formatted_text = f"task: sentence similarity | query: {text}"
        response = await self.client.aio.models.embed_content(
            model=self.embedding_model,
            contents=formatted_text,
            config=types.EmbedContentConfig(output_dimensionality=self.EMBEDDING_DIMENSIONS),
        )
        if not response.embeddings:
            return None
        values = response.embeddings[0].values
        return list(values) if values else None

    async def generate_text(self, prompt: str) -> str | None:
        from google.genai import types

        response = await self.client.aio.models.generate_content(
            model=self.text_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=100,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        return response.text.strip() if response.text else None


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider | None:
    """Return the configured provider, or None if its API key is absent."""
    settings = get_settings()
    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not configured; AI features are disabled.")
            return None
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            embedding_model=settings.openai_embedding_model,
            text_model=settings.openai_text_model,
        )

    if not settings.google_api_key:
        logger.warning("GOOGLE_API_KEY not configured; AI features are disabled.")
        return None
    return GoogleGenAIProvider(
        api_key=settings.google_api_key,
        embedding_model=settings.google_embedding_model,
        text_model=settings.google_text_model,
    )
