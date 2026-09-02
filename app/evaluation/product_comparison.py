"""LLM-as-judge evaluation for the product comparison agent."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.food_search import FoodSearchDependencies
from app.agents.product_comparison import ProductComparisonAgent


class ProductComparisonApproach(StrEnum):
    """Prompting strategies compared by the benchmark."""

    DIRECT = "direct"
    EVIDENCE_TABLE = "evidence_table"


class ProductComparisonEvaluationItem(BaseModel):
    """One comparison question and its expected rubric."""

    question: str
    reference_answer: str


class ProductComparisonEvaluationRecord(BaseModel):
    """Generated answer submitted to the judge."""

    approach: ProductComparisonApproach
    question: str
    reference_answer: str
    agent_answer: str


class ProductComparisonJudgeEvaluation(BaseModel):
    """Structured quality decision from the judge model."""

    score: Literal["good", "bad"]
    reasoning: str = Field(description="Concise explanation for the score")


class ProductComparisonJudge:
    """Judge product comparisons against reference rubrics."""

    def __init__(self, model: Any) -> None:
        """Create a structured-output judge agent."""
        self.agent: Agent[None, ProductComparisonJudgeEvaluation] = Agent(
            model,
            output_type=ProductComparisonJudgeEvaluation,
            instructions=(
                "Evaluate product comparisons against the question and rubric. "
                "Require correct product identity, sources, nutrient comparisons, "
                "and accurate ingredient or allergen claims. Penalize invention."
            ),
        )

    async def evaluate(
        self, record: ProductComparisonEvaluationRecord
    ) -> ProductComparisonJudgeEvaluation:
        """Evaluate one generated comparison."""
        result = await self.agent.run(
            f"Question:\n{record.question}\n\n"
            f"Reference rubric:\n{record.reference_answer}\n\n"
            f"Agent answer ({record.approach.value}):\n{record.agent_answer}"
        )
        return result.output


@dataclass
class ProductComparisonEvaluationRunner:
    """Generate and judge product comparisons for each approach."""

    dependencies: FoodSearchDependencies
    judge: ProductComparisonJudge

    async def run(
        self,
        items: list[ProductComparisonEvaluationItem],
        approaches: list[ProductComparisonApproach],
    ) -> list[tuple[ProductComparisonEvaluationRecord, ProductComparisonJudgeEvaluation]]:
        """Run all benchmark questions through all approaches."""
        if len(approaches) < 2:
            raise ValueError("Product comparison evaluation requires two approaches")
        results = []
        for approach in approaches:
            instructions = {
                ProductComparisonApproach.DIRECT: "Use the tool and answer directly.",
                ProductComparisonApproach.EVIDENCE_TABLE: (
                    "Use the tool and explain the comparison with a compact "
                    "evidence table before giving the ranking."
                ),
            }[approach]
            agent = ProductComparisonAgent(instructions=instructions)
            for item in items:
                response = await agent.run(item.question, deps=self.dependencies)
                record = ProductComparisonEvaluationRecord(
                    approach=approach,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    agent_answer=response.output.answer,
                )
                results.append((record, await self.judge.evaluate(record)))
        return results


def load_dataset(path: Path) -> list[ProductComparisonEvaluationItem]:
    """Load and validate product comparison examples from JSON."""
    return [
        ProductComparisonEvaluationItem.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def summarize_results(
    results: list[
        tuple[ProductComparisonEvaluationRecord, ProductComparisonJudgeEvaluation]
    ],
) -> list[dict[str, str | int | float]]:
    """Calculate judge pass rates per comparison approach."""
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
