"""Application configuration loaded from environment variables and YAML."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class UsageLimitsSettings(BaseModel):
    """Request and tool-call limits for one PydanticAI execution."""

    request_limit: int | None = None
    tool_calls_limit: int | None = None


class ModelSettings(BaseModel):
    """Configuration for one model role."""

    provider: Literal["openai", "vertex"]
    model: str
    timeout_seconds: float | None = None
    max_output_tokens: int | None = None
    usage_limits: UsageLimitsSettings = UsageLimitsSettings()


class ModelsSettings(BaseModel):
    """Configuration for all model roles used by the application."""

    query_rewriter: ModelSettings
    planner: ModelSettings
    agent: ModelSettings
    synthesis: ModelSettings
    evaluation_judge: ModelSettings
    embeddings: ModelSettings


class Settings(BaseSettings):
    """Runtime settings for FoodMind services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file=Path("app/models.yaml"),
        env_nested_delimiter="__",
        extra="ignore",
    )

    models: ModelsSettings

    ELASTICSEARCH_URL: str = "http://localhost:9200"
    DATABASE_URL: str = "postgresql+psycopg://foodmind:foodmind@localhost:5432/foodmind"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "openai:gpt-5-mini"
    OPENAI_PLANNER_MODEL: str | None = None
    OPENAI_QUERY_REWRITER_MODEL: str | None = None
    OPENAI_AGENT_MODEL: str | None = None
    OPENAI_SYNTHESIS_MODEL: str | None = None
    PLANNER_TIMEOUT_SECONDS: float = 30.0
    QUERY_REWRITE_TIMEOUT_SECONDS: float = 15.0
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Define configuration source precedence.

        Environment variables and ``.env`` values override the checked-in YAML
        defaults, while constructor arguments remain the highest-priority source.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Create and cache the application settings instance."""
    return Settings()
