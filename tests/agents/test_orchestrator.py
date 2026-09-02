"""Unit tests for orchestrator delegation guardrails."""

import pytest

from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies
from app.agents.execution_state import ExecutionState
from app.agents.planner import DelegationTask, ExecutionPlan, AgentName, PlannedTask


def test_delegation_task_requires_structured_objective() -> None:
    """Delegation requests expose objective, context, and required fields."""
    task = DelegationTask(
        objective="Compare products",
        context="Use the products returned by search",
        required_fields=["protein", "allergens"],
    )

    assert task.required_fields == ["protein", "allergens"]


def test_execution_plan_rejects_cycles() -> None:
    """Planner output cannot contain cyclic task dependencies."""
    with pytest.raises(ValueError, match="acyclic"):
        ExecutionPlan(
            tasks=[
                PlannedTask(
                    id="search",
                    agent=AgentName.FOOD_SEARCH,
                    task=DelegationTask(objective="Search"),
                    depends_on=["compare"],
                ),
                PlannedTask(
                    id="compare",
                    agent=AgentName.PRODUCT_COMPARISON,
                    task=DelegationTask(objective="Compare"),
                    depends_on=["search"],
                ),
            ]
        )


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


def test_execution_state_rejects_duplicate_steps_and_records_evidence() -> None:
    """Execution state prevents duplicate work and preserves tool evidence."""
    state = ExecutionState(original_query="Find apples")
    state.select_agent("food_search")
    state.start_step("food_search:Find apples")
    state.complete_step("food_search:Find apples", {"id": "1", "label": "Apple"})

    with pytest.raises(ValueError, match="already attempted"):
        state.start_step("food_search:Find apples")

    assert state.selected_agents == ["food_search"]
    assert state.completed_steps == ["food_search:Find apples"]
    assert state.retrieved_evidence["food_search:Find apples"][0]["id"] == "1"
