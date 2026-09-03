"""Live LLM-as-judge evaluation for the food recommendation agent."""

import asyncio
from pathlib import Path

import pytest

from app.agents.food_search import FoodSearchDependencies
from app.evaluation.food_recommendation import (
    FoodRecommendationEvaluationRunner,
    FoodRecommendationJudge,
    RecommendationApproach,
    load_dataset,
    summarize_results,
)
from app.settings import get_settings
from app.evaluation.artifacts import EvaluationArtifactRepository


@pytest.mark.evaluation
def test_food_recommendation_llm_evaluation(evaluation_catalog: str) -> None:
    """Compare recommendation prompting strategies against fixture data."""
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")

    async def evaluate() -> object:
        from elasticsearch import AsyncElasticsearch

        client = AsyncElasticsearch(evaluation_catalog)
        try:
            runner = FoodRecommendationEvaluationRunner(
                dependencies=FoodSearchDependencies.from_client(client),
                judge=FoodRecommendationJudge(model=get_settings().OPENAI_MODEL),
            )
            return await runner.run(
                load_dataset(Path(__file__).parent / "food_recommendation_dataset.json"),
                [RecommendationApproach.DIRECT, RecommendationApproach.CONSTRAINTS_EXPLICIT],
            )
        finally:
            await client.close()

    results = asyncio.run(evaluate())
    summary = summarize_results(results)  # type: ignore[arg-type]
    asyncio.run(EvaluationArtifactRepository().save("food-recommendation", summary, str(summary[0]["approach"])))
    assert len(summary) == 2
    assert all(row["total"] == 2 for row in summary)
