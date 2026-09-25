from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://dpp:dpp@localhost:5432/dpp"
    session_secret: str = "dev-only-insecure-secret-change-me"
    ai_provider: Literal["openai", "google"] = "openai"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_text_model: str = "gpt-4o-mini"
    google_api_key: str | None = None
    google_embedding_model: str = "gemini-embedding-2"
    google_text_model: str = "gemini-3.5-flash-lite"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
