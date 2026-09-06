"""Minimal FoodMind agent backed by the configured provider through PydanticAI."""

from pydantic_ai import Agent

from app.aggregates.model_configuration import ModelRole
from app.agents.model_factory import ModelFactory
from app.settings import get_settings


async def ask_foodmind(prompt: str) -> str:
    """Send one prompt to the FoodMind agent and return its text response."""
    settings = get_settings()
    agent = Agent(
        ModelFactory(settings).build(ModelRole.AGENT),
        instructions=(
            "You are a helpful food assistant. Answer briefly and clearly. "
            "If a question is unrelated to food, say so."
        ),
    )
    result = await agent.run(prompt)
    return result.output
