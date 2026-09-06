"""Tests for provider-aware model construction."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.aggregates.model_configuration import ModelRole
from app.agents.model_factory import ModelFactory
from app.settings import ModelSettings


def _settings(provider: str, model: str, **credentials: str | None) -> SimpleNamespace:
    """Build a minimal settings double for factory tests."""
    return SimpleNamespace(
        models=SimpleNamespace(
            agent=ModelSettings(provider=provider, model=model),
            planner=ModelSettings(provider=provider, model=model),
            query_rewriter=ModelSettings(provider=provider, model=model),
            synthesis=ModelSettings(provider=provider, model=model),
            evaluation_judge=ModelSettings(provider=provider, model=model),
            embeddings=ModelSettings(provider=provider, model=model),
        ),
        OPENAI_API_KEY=credentials.get("openai_api_key"),
        GEMINI_API_KEY=credentials.get("gemini_api_key"),
    )


def test_openai_model_is_provider_qualified_without_credentials() -> None:
    """OpenAI construction can be deferred when no key is configured."""
    settings = _settings("openai", "gpt-4.1-mini")

    factory = ModelFactory(settings)
    assert factory.name_for(ModelRole.AGENT) == "openai:gpt-4.1-mini"
    assert factory.build(ModelRole.AGENT) == "openai:gpt-4.1-mini"


def test_vertex_model_uses_google_cloud_provider() -> None:
    """Vertex roles construct a Google Cloud model using application credentials."""
    settings = _settings("vertex", "gemini-2.5-flash")

    factory = ModelFactory(settings)
    with patch("app.agents.model_factory.GoogleModel") as google_model:
        model = factory.build(ModelRole.PLANNER)

    google_model.assert_called_once_with("gemini-2.5-flash", provider="google-cloud")
    assert model is google_model.return_value
    assert factory.name_for(ModelRole.PLANNER) == "vertex:gemini-2.5-flash"


def test_gemini_provider_requires_api_key() -> None:
    """The Gemini API provider fails clearly when its key is absent."""
    settings = _settings("gemini", "gemini-2.5-flash")

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        ModelFactory(settings).build(ModelRole.AGENT)
