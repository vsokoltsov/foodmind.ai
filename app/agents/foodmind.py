"""Minimal FoodMind agent backed by an OpenAI model through PydanticAI."""

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.settings import get_settings


def _create_model() -> OpenAIChatModel:
    """Create the configured OpenAI model provider."""
    settings = get_settings()
    return OpenAIChatModel(
        settings.OPENAI_MODEL.removeprefix("openai:"),
        provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
    )


def create_foodmind_agent() -> Agent[None, str]:
    """Create the basic text FoodMind agent."""
    return Agent(
        _create_model(),
        instructions=(
            "You are a helpful food assistant. Answer briefly and clearly. "
            "If a question is unrelated to food, say so."
        ),
    )


async def ask_foodmind(prompt: str) -> str:
    """Send one prompt to the FoodMind agent and return its text response."""
    result = await create_foodmind_agent().run(prompt)
    return result.output
