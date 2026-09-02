"""Live LLM-as-judge evaluation for the FoodMind planner."""

import asyncio
from pathlib import Path

import pytest

from app.evaluation.planner import (
    PlannerApproach,
    PlannerEvaluationRunner,
    PlannerJudge,
    load_dataset,
    summarize_results,
)
from app.settings import get_settings


@pytest.mark.evaluation
def test_planner_llm_evaluation() -> None:
    """Compare direct and dependency-aware planning strategies."""
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")

    async def evaluate() -> object:
        runner = PlannerEvaluationRunner(
            judge=PlannerJudge(model=get_settings().OPENAI_MODEL)
        )
        return await runner.run(
            load_dataset(Path(__file__).parent / "planner_dataset.json"),
            [PlannerApproach.DIRECT, PlannerApproach.DEPENDENCY_AWARE],
        )

    results = asyncio.run(evaluate())
    summary = summarize_results(results)  # type: ignore[arg-type]
    assert len(summary) == 2
    assert all(row["total"] == 2 for row in summary)
