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
    DATABASE_URL: str = "postgresql+psycopg://foodmind:foodmind@localhost:5432/foodmind"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "openai:gpt-5-mini"
    OPENAI_PLANNER_MODEL: str | None = None
    OPENAI_AGENT_MODEL: str | None = None
    OPENAI_SYNTHESIS_MODEL: str | None = None
    PLANNER_TIMEOUT_SECONDS: float = 30.0
    AGENT_TIMEOUT_SECONDS: float = 120.0
    SYNTHESIS_TIMEOUT_SECONDS: float = 60.0
    RETRIEVAL_TIMEOUT_SECONDS: float = 5.0
    MAX_RETRIEVAL_RESULTS: int = 10
    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "foodmind-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS: float = 10.0
    NATS_URL: str = "nats://localhost:4222"
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
