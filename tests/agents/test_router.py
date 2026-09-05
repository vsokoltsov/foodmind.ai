"""Tests for low-latency deterministic request routing."""

import pytest

from app.agents.planner import AgentName
from app.agents.router import FoodMindRouter, RouteKind


@pytest.mark.parametrize(
    ("prompt", "agent"),
    [
        ("How much protein does tofu contain?", AgentName.NUTRITION_ANALYSIS),
        ("Compare these two cereal products", AgentName.PRODUCT_COMPARISON),
        ("Recommend vegan foods without peanuts", AgentName.FOOD_RECOMMENDATION),
        ("Find Italian food categories", AgentName.FOOD_SEARCH),
    ],
)
def test_router_bypasses_planning_for_clear_single_agent_intents(
    prompt: str, agent: AgentName
) -> None:
    """Clear intents route directly to one specialist."""
    route = FoodMindRouter().route(prompt)

    assert route.kind is RouteKind.DIRECT
    assert route.agent is agent


def test_router_uses_planner_for_ambiguous_request() -> None:
    """Requests without a reliable deterministic signal remain planned."""
    route = FoodMindRouter().route("What should I make for dinner?")

    assert route.kind is RouteKind.PLANNED
    assert route.agent is None
