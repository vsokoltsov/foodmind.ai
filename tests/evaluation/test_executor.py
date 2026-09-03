"""Live LLM-as-judge evaluation for the plan executor."""

import asyncio
from pathlib import Path

import pytest

from app.agents.food_search import FoodSearchDependencies
from app.evaluation.executor import (
    ExecutorApproach,
    ExecutorEvaluationRunner,
    ExecutorJudge,
    load_dataset,
    summarize_results,
)
from app.settings import get_settings
from app.evaluation.artifacts import EvaluationArtifactRepository


@pytest.mark.evaluation
def test_executor_llm_evaluation(evaluation_catalog: str) -> None:
    """Compare minimal and evidence-rich execution against fixture data."""
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")

    async def evaluate() -> object:
        from elasticsearch import AsyncElasticsearch

        client = AsyncElasticsearch(evaluation_catalog)
        try:
            runner = ExecutorEvaluationRunner(
                repositories=FoodSearchDependencies.from_client(client),
                judge=ExecutorJudge(model=get_settings().OPENAI_MODEL),
            )
            return await runner.run(
                load_dataset(Path(__file__).parent / "executor_dataset.json"),
                [ExecutorApproach.MINIMAL, ExecutorApproach.EVIDENCE_RICH],
            )
        finally:
            await client.close()

    results = asyncio.run(evaluate())
    summary = summarize_results(results)  # type: ignore[arg-type]
    asyncio.run(EvaluationArtifactRepository().save("executor", summary, str(summary[0]["approach"])))
    assert len(summary) == 2
    assert all(row["total"] == 1 for row in summary)
