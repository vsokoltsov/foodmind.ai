"""Tests for FoodMind LLM evaluation bookkeeping."""

import pytest

from app.evaluation.food_search import (
    EvaluationItem,
    EvaluationRecord,
    FoodSearchApproach,
    FoodSearchJudge,
    JudgeEvaluation,
    summarize_results,
)


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
