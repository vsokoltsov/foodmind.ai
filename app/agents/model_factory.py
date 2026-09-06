"""Provider-aware construction of PydanticAI models."""

from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.aggregates.model_configuration import ModelProvider, ModelRole
from app.settings import ModelSettings, Settings


@dataclass(frozen=True)
class ModelFactory:
    """Build configured models for each FoodMind component."""

    settings: Settings

    def settings_for(self, role: ModelRole) -> ModelSettings:
        """Return the typed configuration assigned to a model role."""
        match role:
            case ModelRole.QUERY_REWRITER:
                return self.settings.models.query_rewriter
            case ModelRole.PLANNER:
                return self.settings.models.planner
            case ModelRole.AGENT:
                return self.settings.models.agent
            case ModelRole.SYNTHESIS:
                return self.settings.models.synthesis
            case ModelRole.EVALUATION_JUDGE:
                return self.settings.models.evaluation_judge
            case ModelRole.EMBEDDINGS:
                return self.settings.models.embeddings

    def name_for(self, role: ModelRole) -> str:
        """Return a provider-qualified model name for logs and metrics."""
        configuration = self.settings_for(role)
        return f"{configuration.provider}:{configuration.model}"

    def build(self, role: ModelRole) -> Model | str:
        """Build a PydanticAI model using the role's configured provider."""
        configuration = self.settings_for(role)
        match configuration.provider:
            case ModelProvider.OPENAI:
                if self.settings.OPENAI_API_KEY:
                    return OpenAIChatModel(
                        model_name=configuration.model,
                        provider=OpenAIProvider(api_key=self.settings.OPENAI_API_KEY),
                    )
                return f"openai:{configuration.model}"
            case ModelProvider.VERTEX:
                return GoogleModel(configuration.model, provider="google-cloud")
            case ModelProvider.GEMINI:
                if not self.settings.GEMINI_API_KEY:
                    raise ValueError(
                        "GEMINI_API_KEY is required for the Gemini API provider"
                    )
                return GoogleModel(
                    configuration.model,
                    provider=GoogleProvider(api_key=self.settings.GEMINI_API_KEY),
                )

    def defer_model_check(self) -> bool:
        """Return whether PydanticAI should defer provider validation."""
        return not bool(self.settings.OPENAI_API_KEY)

    def provider_is_configured(self, role: ModelRole) -> bool:
        """Return whether the configured role can make a provider request."""
        configuration = self.settings_for(role)
        match configuration.provider:
            case ModelProvider.VERTEX:
                return True
            case ModelProvider.GEMINI:
                return bool(self.settings.GEMINI_API_KEY)
            case ModelProvider.OPENAI:
                return bool(self.settings.OPENAI_API_KEY)
