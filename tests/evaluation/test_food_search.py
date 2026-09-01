"""Tests for FoodMind bookkeeping and live LLM-as-judge evaluation."""

import asyncio
from pathlib import Path

import pytest

from app.evaluation.food_search import (
    EvaluationItem,
    EvaluationRecord,
    FoodSearchApproach,
    FoodSearchJudge,
    JudgeEvaluation,
    summarize_results,
)
from app.agents.food_search import FoodSearchDependencies
from app.evaluation.food_search import FoodSearchEvaluationRunner, load_dataset
from app.settings import get_settings


def test_summary_selects_highest_approach_rate() -> None:
    """Summaries rank approaches by judge pass rate."""
    results = [
        (
            EvaluationRecord(
                approach=FoodSearchApproach.DIRECT,
                question="q1",
                reference_answer="a",
                agent_answer="a",
            ),
            JudgeEvaluation(score="good", reasoning="correct"),
        ),
        (
            EvaluationRecord(
                approach=FoodSearchApproach.EVIDENCE_FIRST,
                question="q1",
                reference_answer="a",
                agent_answer="wrong",
            ),
            JudgeEvaluation(score="bad", reasoning="wrong"),
        ),
    ]

    summary = summarize_results(results)

    assert summary[0]["approach"] == "direct"
    assert summary[0]["good_rate"] == 1.0


def test_judge_requires_structured_output_model() -> None:
    """The judge exposes a PydanticAI agent with typed output."""
    judge = FoodSearchJudge(model="test")

    assert judge.agent.output_type is JudgeEvaluation


def test_dataset_item_is_validated() -> None:
    """Evaluation examples require both a question and reference answer."""
    assert EvaluationItem(question="q", reference_answer="a").question == "q"

    with pytest.raises(ValueError):
        EvaluationItem.model_validate({"question": "q"})


@pytest.mark.evaluation
def test_food_search_llm_evaluation(evaluation_catalog: str) -> None:
    """Compare two prompts against seeded Elasticsearch using a real judge."""
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")

    async def evaluate() -> list[tuple[EvaluationRecord, JudgeEvaluation]]:
        from elasticsearch import AsyncElasticsearch

        client = AsyncElasticsearch(evaluation_catalog)
        try:
            dependencies = FoodSearchDependencies.from_client(client)
            runner = FoodSearchEvaluationRunner(
                dependencies=dependencies,
                judge=FoodSearchJudge(model=get_settings().OPENAI_MODEL),
            )
            return await runner.run(
                load_dataset(
                    Path(__file__).parent / "food_search_dataset.json"
                ),
                [FoodSearchApproach.DIRECT, FoodSearchApproach.EVIDENCE_FIRST],
            )
        finally:
            await client.close()

    results = asyncio.run(evaluate())
    summary = summarize_results(results)

    assert len(results) == 6
    assert len(summary) == 2
    assert all(row["total"] == 3 for row in summary)
