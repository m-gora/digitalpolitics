import logging
from typing import Protocol

from dpp.config import get_settings

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str: ...


class GoogleTranscriber:
    """Voice transcription via Gemini (google-genai).

    Audio is sent inline as a multimodal part together with a verbatim
    transcription prompt; it is never stored anywhere.
    """

    PROMPT = (
        "Transkribiere die folgende Sprachaufnahme wörtlich auf Deutsch. "
        "Gebe ausschließlich den Transkripttext zurück, ohne Einleitung, "
        "Kommentare oder Formatierung."
    )

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        from google.genai import types

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=audio, mime_type=content_type),
                self.PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        return response.text.strip() if response.text else ""


def get_transcriber() -> Transcriber | None:
    settings = get_settings()
    if not settings.google_api_key:
        return None
    return GoogleTranscriber(settings.google_api_key, settings.google_transcribe_model)
