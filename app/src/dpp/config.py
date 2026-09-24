from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://dpp:dpp@localhost:5432/dpp"
    session_secret: str = "dev-only-insecure-secret-change-me"
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
