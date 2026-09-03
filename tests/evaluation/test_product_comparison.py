"""Live LLM-as-judge evaluation for the product comparison agent."""

import asyncio
from pathlib import Path

import pytest

from app.agents.food_search import FoodSearchDependencies
from app.evaluation.product_comparison import (
    ProductComparisonApproach,
    ProductComparisonEvaluationRunner,
    ProductComparisonJudge,
    load_dataset,
    summarize_results,
)
from app.settings import get_settings
from app.evaluation.artifacts import EvaluationArtifactRepository


@pytest.mark.evaluation
def test_product_comparison_llm_evaluation(evaluation_catalog: str) -> None:
    """Compare product-comparison prompting strategies against fixture data."""
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")

    async def evaluate() -> object:
        from elasticsearch import AsyncElasticsearch

        client = AsyncElasticsearch(evaluation_catalog)
        try:
            runner = ProductComparisonEvaluationRunner(
                dependencies=FoodSearchDependencies.from_client(client),
                judge=ProductComparisonJudge(model=get_settings().OPENAI_MODEL),
            )
            return await runner.run(
                load_dataset(Path(__file__).parent / "product_comparison_dataset.json"),
                [ProductComparisonApproach.DIRECT, ProductComparisonApproach.EVIDENCE_TABLE],
            )
        finally:
            await client.close()

    results = asyncio.run(evaluate())
    summary = summarize_results(results)  # type: ignore[arg-type]
    asyncio.run(EvaluationArtifactRepository().save("product-comparison", summary, str(summary[0]["approach"])))
    assert len(summary) == 2
    assert all(row["total"] == 2 for row in summary)
