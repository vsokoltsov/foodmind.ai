"""LLM-as-judge evaluation for the nutrition analysis agent."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded

from app.agents.food_search import FoodSearchDependencies
from app.agents.nutrition_analysis import NutritionAnalysisAgent


class NutritionApproach(StrEnum):
    """Prompting strategies compared by the nutrition benchmark."""

    DIRECT = "direct"
    EXPLICIT_UNITS = "explicit_units"


class NutritionEvaluationItem(BaseModel):
    """One nutrition question and its expected rubric."""

    question: str
    reference_answer: str


class NutritionEvaluationRecord(BaseModel):
    """Generated nutrition answer submitted to the judge."""

    approach: NutritionApproach
    question: str
    reference_answer: str
    agent_answer: str


class NutritionJudgeEvaluation(BaseModel):
    """Structured quality decision from the judge model."""

    score: Literal["good", "bad"]
    reasoning: str = Field(description="Concise explanation for the score")


class NutritionAnalysisJudge:
    """Judge nutrition answers against reference rubrics."""

    def __init__(self, model: Any) -> None:
        """Create a structured-output judge agent."""
        self.agent: Agent[None, NutritionJudgeEvaluation] = Agent(
            model,
            output_type=NutritionJudgeEvaluation,
            instructions=(
                "Evaluate nutrition answers against the question and reference "
                "rubric. Require correct food matching, requested nutrients, "
                "and clear units. Do not reward invented values."
            ),
        )

    async def evaluate(
        self, record: NutritionEvaluationRecord
    ) -> NutritionJudgeEvaluation:
        """Evaluate one generated answer."""
        result = await self.agent.run(
            f"Question:\n{record.question}\n\n"
            f"Reference rubric:\n{record.reference_answer}\n\n"
            f"Agent answer ({record.approach.value}):\n{record.agent_answer}"
        )
        return result.output


@dataclass
class NutritionEvaluationRunner:
    """Generate and judge nutrition answers for multiple approaches."""

    dependencies: FoodSearchDependencies
    judge: NutritionAnalysisJudge

    async def run(
        self,
        items: list[NutritionEvaluationItem],
        approaches: list[NutritionApproach],
    ) -> list[tuple[NutritionEvaluationRecord, NutritionJudgeEvaluation]]:
        """Run every approach against every benchmark item."""
        if len(approaches) < 2:
            raise ValueError("Nutrition evaluation requires at least two approaches")
        results = []
        for approach in approaches:
            instructions = {
                NutritionApproach.DIRECT: "Use the tool and answer directly.",
                NutritionApproach.EXPLICIT_UNITS: (
                    "Use the tool, explain unit normalization, and show the "
                    "nutrient name, amount, and unit for every requested value."
                ),
            }[approach]
            agent = NutritionAnalysisAgent(instructions=instructions)
            for item in items:
                try:
                    response = await agent.run(
                        item.question,
                        deps=self.dependencies,
                        usage_limits=UsageLimits(request_limit=12, tool_calls_limit=4),
                    )
                    answer = response.output.answer
                except UsageLimitExceeded as exc:
                    answer = f"Evaluation stopped before a final answer: {exc}"
                record = NutritionEvaluationRecord(
                    approach=approach,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    agent_answer=answer,
                )
                results.append((record, await self.judge.evaluate(record)))
        return results


def load_dataset(path: Path) -> list[NutritionEvaluationItem]:
    """Load and validate nutrition evaluation examples from JSON."""
    return [
        NutritionEvaluationItem.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def summarize_results(
    results: list[tuple[NutritionEvaluationRecord, NutritionJudgeEvaluation]],
) -> list[dict[str, str | int | float]]:
    """Calculate judge pass rates per nutrition approach."""
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
