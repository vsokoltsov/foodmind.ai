"""Unit tests for dependency-aware plan execution."""

import asyncio
from types import SimpleNamespace

from app.agents.executor import PlanExecutor
from app.agents.food_search import FoodSearchAnswer, FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies
from app.agents.planner import AgentName, DelegationTask, ExecutionPlan, PlannedTask


class _FakeAgent:
    """Minimal specialist double returning a typed answer."""

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, prompt: str, *, deps: object) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(output=FoodSearchAnswer(answer=prompt))


def _dependencies(agent: _FakeAgent) -> OrchestratorDependencies:
    """Build orchestrator dependencies around a fake specialist."""
    return OrchestratorDependencies(
        repositories=FoodSearchDependencies(
            wikidata=None, usda=None, openfoodfacts=None  # type: ignore[arg-type]
        ),
        food_search=agent,  # type: ignore[arg-type]
        nutrition_analysis=agent,  # type: ignore[arg-type]
        product_comparison=agent,  # type: ignore[arg-type]
        food_recommendation=agent,  # type: ignore[arg-type]
    )


def test_executor_passes_dependency_results_and_caches_identical_tasks() -> None:
    """Dependent tasks receive prior output and identical requests are cached."""
    agent = _FakeAgent()
    dependencies = _dependencies(agent)
    plan = ExecutionPlan(
        tasks=[
            PlannedTask(
                id="search",
                agent=AgentName.FOOD_SEARCH,
                task=DelegationTask(objective="Find foods"),
            ),
            PlannedTask(
                id="follow_up",
                agent=AgentName.NUTRITION_ANALYSIS,
                task=DelegationTask(objective="Analyze results"),
                depends_on=["search"],
            ),
        ]
    )

    executor = PlanExecutor()
    report = asyncio.run(
        executor.execute(plan, prompt="User request", dependencies=dependencies)
    )

    assert len(report.successful) == 2
    cached_report = asyncio.run(
        executor.execute(plan, prompt="User request", dependencies=dependencies)
    )
    assert cached_report.tasks[0].cached
    assert agent.calls == 2
    assert "Find foods" in report.tasks[1].output.answer  # type: ignore[union-attr]
