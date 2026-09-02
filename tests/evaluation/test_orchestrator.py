"""Live LLM-as-judge evaluation for the FoodMind orchestrator."""

import asyncio
from pathlib import Path

import pytest

from app.agents.food_search import FoodSearchDependencies
from app.evaluation.orchestrator import (
    OrchestratorApproach,
    OrchestratorEvaluationRunner,
    OrchestratorJudge,
    load_dataset,
    summarize_results,
)
from app.settings import get_settings


@pytest.mark.evaluation
def test_orchestrator_llm_evaluation(evaluation_catalog: str) -> None:
    """Compare direct and plan-first orchestration against fixture data."""
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")

    async def evaluate() -> object:
        from elasticsearch import AsyncElasticsearch

        client = AsyncElasticsearch(evaluation_catalog)
        try:
            runner = OrchestratorEvaluationRunner(
                repositories=FoodSearchDependencies.from_client(client),
                judge=OrchestratorJudge(model=get_settings().OPENAI_MODEL),
            )
            return await runner.run(
                load_dataset(Path(__file__).parent / "orchestrator_dataset.json"),
                [OrchestratorApproach.DIRECT, OrchestratorApproach.PLAN_FIRST],
            )
        finally:
            await client.close()

    results = asyncio.run(evaluate())
    summary = summarize_results(results)  # type: ignore[arg-type]
    assert len(summary) == 2
    assert all(row["total"] == 2 for row in summary)
