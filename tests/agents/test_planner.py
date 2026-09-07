"""Tests for resilient FoodMind execution planning."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2

from app.agents.planner import AgentName, ExecutionPlan, FoodMindPlanner, PlannedTask
from app.settings import ModelSettings
from tests.repositories.conftest import run


def test_planner_retries_transient_transport_errors(monkeypatch) -> None:
    """A temporary provider connection error is retried before planning fails."""
    settings = SimpleNamespace(
        OPENAI_API_KEY=None,
        models=SimpleNamespace(
            planner=ModelSettings(provider="openai", model="test-model")
        ),
    )
    monkeypatch.setattr("app.agents.planner.get_settings", lambda: settings)

    async def scenario() -> None:
        planner = FoodMindPlanner(retry_base_delay_seconds=0.01)
        expected_plan = ExecutionPlan(
            tasks=[
                PlannedTask(
                    id="search_foods",
                    agent=AgentName.FOOD_SEARCH,
                    task={"objective": "Find matching foods."},
                )
            ]
        )
        expected_result = SimpleNamespace(
            output=expected_plan,
            usage=SimpleNamespace(input_tokens=4, output_tokens=3),
        )
        planner.agent.run = AsyncMock(
            side_effect=[httpx2.ConnectError("temporary connection failure"), expected_result]
        )
        sleep = AsyncMock()
        monkeypatch.setattr("app.agents.planner.asyncio.sleep", sleep)

        result = await planner.plan("Find high-protein foods")

        assert result is expected_result
        assert planner.agent.run.await_count == 2
        sleep.assert_awaited_once_with(0.01)

    run(scenario())
