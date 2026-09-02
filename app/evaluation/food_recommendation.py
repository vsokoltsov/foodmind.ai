"""LLM-as-judge evaluation for the food recommendation agent."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.food_recommendation import FoodRecommendationAgent
from app.agents.food_search import FoodSearchDependencies


class RecommendationApproach(StrEnum):
    """Prompting strategies compared by the benchmark."""

    DIRECT = "direct"
    CONSTRAINTS_EXPLICIT = "constraints_explicit"


class RecommendationEvaluationItem(BaseModel):
    """One recommendation question and its expected rubric."""

    question: str
    reference_answer: str


class RecommendationEvaluationRecord(BaseModel):
    """Generated recommendation submitted to the judge."""

    approach: RecommendationApproach
    question: str
    reference_answer: str
    agent_answer: str


class RecommendationJudgeEvaluation(BaseModel):
    """Structured quality decision from the judge model."""

    score: Literal["good", "bad"]
    reasoning: str = Field(description="Concise explanation for the score")


class FoodRecommendationJudge:
    """Judge recommendations against constraint-based reference rubrics."""

    def __init__(self, model: Any) -> None:
        """Create a structured-output judge agent."""
        self.agent: Agent[None, RecommendationJudgeEvaluation] = Agent(
            model,
            output_type=RecommendationJudgeEvaluation,
            instructions=(
                "Evaluate food recommendations against the question and rubric. "
                "Require that constraints are respected, returned sources are "
                "identified, and unsupported claims are not invented."
            ),
        )

    async def evaluate(
        self, record: RecommendationEvaluationRecord
    ) -> RecommendationJudgeEvaluation:
        """Evaluate one generated recommendation."""
        result = await self.agent.run(
            f"Question:\n{record.question}\n\n"
            f"Reference rubric:\n{record.reference_answer}\n\n"
            f"Agent answer ({record.approach.value}):\n{record.agent_answer}"
        )
        return result.output


@dataclass
class FoodRecommendationEvaluationRunner:
    """Generate and judge recommendations for multiple prompting approaches."""

    dependencies: FoodSearchDependencies
    judge: FoodRecommendationJudge

    async def run(
        self,
        items: list[RecommendationEvaluationItem],
        approaches: list[RecommendationApproach],
    ) -> list[tuple[RecommendationEvaluationRecord, RecommendationJudgeEvaluation]]:
        """Run every benchmark item through every approach."""
        if len(approaches) < 2:
            raise ValueError("Recommendation evaluation requires two approaches")
        results = []
        for approach in approaches:
            instructions = {
                RecommendationApproach.DIRECT: "Use the tool and answer directly.",
                RecommendationApproach.CONSTRAINTS_EXPLICIT: (
                    "Use the tool, enumerate each constraint checked, and explain "
                    "why every recommendation satisfies it."
                ),
            }[approach]
            agent = FoodRecommendationAgent(instructions=instructions)
            for item in items:
                response = await agent.run(item.question, deps=self.dependencies)
                record = RecommendationEvaluationRecord(
                    approach=approach,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    agent_answer=response.output.answer,
                )
                results.append((record, await self.judge.evaluate(record)))
        return results


def load_dataset(path: Path) -> list[RecommendationEvaluationItem]:
    """Load and validate recommendation benchmark items from JSON."""
    return [
        RecommendationEvaluationItem.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def summarize_results(
    results: list[tuple[RecommendationEvaluationRecord, RecommendationJudgeEvaluation]],
) -> list[dict[str, str | int | float]]:
    """Calculate judge pass rates for each recommendation approach."""
    summary = []
    for approach in sorted({record.approach for record, _ in results}, key=str):
        rows = [item for item in results if item[0].approach == approach]
        good = sum(evaluation.score == "good" for _, evaluation in rows)
        summary.append(
            {
                "approach": approach.value,
                "total": len(rows),
                "good": good,
                "good_rate": good / len(rows) if rows else 0.0,
            }
        )
    return sorted(summary, key=lambda row: (row["good_rate"], row["good"]), reverse=True)
