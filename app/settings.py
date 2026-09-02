"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for FoodMind services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ELASTICSEARCH_URL: str = "http://localhost:9200"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "openai:gpt-5-mini"
    INGESTION_ARTIFACT_STORAGE: Literal["local", "gcs"] = "local"
    GCS_BUCKET: str | None = None
    GCS_PREFIX: str = "foodmind/ingestion"
    GCP_PROJECT_ID: str | None = None
    EVALUATION_ARTIFACT_BUCKET: str | None = None
    EVALUATION_ARTIFACT_PREFIX: str = "foodmind/evaluation"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Create and cache the application settings instance."""
    return Settings()
