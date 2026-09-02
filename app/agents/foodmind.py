"""Minimal FoodMind agent backed by an OpenAI model through PydanticAI."""

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.settings import get_settings


async def ask_foodmind(prompt: str) -> str:
    """Send one prompt to the FoodMind agent and return its text response."""
    settings = get_settings()
    agent = Agent(
        OpenAIChatModel(
            settings.OPENAI_MODEL.removeprefix("openai:"),
            provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
        ),
        instructions=(
            "You are a helpful food assistant. Answer briefly and clearly. "
            "If a question is unrelated to food, say so."
        ),
    )
    result = await agent.run(prompt)
    return result.output
