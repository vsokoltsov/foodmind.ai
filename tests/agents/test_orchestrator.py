"""Unit tests for orchestrator delegation guardrails."""

import pytest

from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies


def _dependencies() -> OrchestratorDependencies:
    """Create dependencies without invoking any model requests."""
    return OrchestratorDependencies.from_repositories(
        FoodSearchDependencies(wikidata=None, usda=None, openfoodfacts=None)  # type: ignore[arg-type]
    )


def test_delegation_budget_limits_total_calls() -> None:
    """The orchestrator rejects calls after its total budget is exhausted."""
    dependencies = _dependencies()
    dependencies.max_total_calls = 1
    dependencies.authorize("food_search")

    with pytest.raises(ValueError, match="budget exhausted"):
        dependencies.authorize("nutrition_analysis")


def test_delegation_budget_limits_one_agent() -> None:
    """The orchestrator limits repeated calls to the same specialist."""
    dependencies = _dependencies()
    dependencies.max_calls_per_agent = 1
    dependencies.authorize("food_search")

    with pytest.raises(ValueError, match="food_search"):
        dependencies.authorize("food_search")
