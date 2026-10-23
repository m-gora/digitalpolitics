import io
import logging
from typing import Protocol

from openai import AsyncOpenAI

from dpp.config import get_settings

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str: ...


class OpenAITranscriber:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        result = await self.client.audio.transcriptions.create(
            model=self.model,
            file=(filename, io.BytesIO(audio), content_type),
            language="de",
        )
        return result.text.strip()


def get_transcriber() -> Transcriber | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAITranscriber(settings.openai_api_key, settings.openai_transcribe_model)
