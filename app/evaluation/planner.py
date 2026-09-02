"""LLM-as-judge evaluation for the FoodMind execution planner."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.planner import ExecutionPlan, FoodMindPlanner


class PlannerApproach(StrEnum):
    """Prompting strategies compared by the planner benchmark."""

    DIRECT = "direct"
    DEPENDENCY_AWARE = "dependency_aware"


class PlannerEvaluationItem(BaseModel):
    """One planning question and expected routing constraints."""

    question: str
    expected_agents: list[str]
    expected_dependencies: dict[str, list[str]] = Field(default_factory=dict)


class PlannerEvaluationRecord(BaseModel):
    """Generated execution plan submitted to the judge."""

    approach: PlannerApproach
    question: str
    expected_agents: list[str]
    expected_dependencies: dict[str, list[str]]
    plan: ExecutionPlan


class PlannerJudgeEvaluation(BaseModel):
    """Structured quality decision from the planner judge."""

    score: Literal["good", "bad"]
    reasoning: str = Field(description="Concise explanation for the score")


class PlannerJudge:
    """Judge generated plans against expected routing behavior."""

    def __init__(self, model: Any) -> None:
        """Create a structured-output planner judge."""
        self.agent: Agent[None, PlannerJudgeEvaluation] = Agent(
            model,
            output_type=PlannerJudgeEvaluation,
            instructions=(
                "Evaluate an execution plan against the expected specialist agents "
                "and dependencies. Accept equivalent task IDs and ordering, but "
                "require all necessary capabilities, no unnecessary agents, and "
                "correct dependency relationships."
            ),
        )

    async def evaluate(self, record: PlannerEvaluationRecord) -> PlannerJudgeEvaluation:
        """Evaluate one generated plan."""
        result = await self.agent.run(
            f"Question:\n{record.question}\n\n"
            f"Expected agents:\n{record.expected_agents}\n"
            f"Expected dependencies:\n{record.expected_dependencies}\n\n"
            f"Generated plan:\n{record.plan.model_dump_json()}"
        )
        return result.output


@dataclass
class PlannerEvaluationRunner:
    """Generate and judge plans for multiple planning approaches."""

    judge: PlannerJudge

    async def run(
        self,
        items: list[PlannerEvaluationItem],
        approaches: list[PlannerApproach],
    ) -> list[tuple[PlannerEvaluationRecord, PlannerJudgeEvaluation]]:
        """Run every planning question through every approach."""
        if len(approaches) < 2:
            raise ValueError("Planner evaluation requires two approaches")
        results = []
        for approach in approaches:
            instructions = {
                PlannerApproach.DIRECT: "Return the smallest valid plan for the request.",
                PlannerApproach.DEPENDENCY_AWARE: (
                    "Explicitly identify independent tasks for parallel execution and "
                    "add dependencies only when outputs are required."
                ),
            }[approach]
            planner = FoodMindPlanner(instructions=instructions)
            for item in items:
                response = await planner.plan(item.question)
                record = PlannerEvaluationRecord(
                    approach=approach,
                    question=item.question,
                    expected_agents=item.expected_agents,
                    expected_dependencies=item.expected_dependencies,
                    plan=response.output,
                )
                results.append((record, await self.judge.evaluate(record)))
        return results


def load_dataset(path: Path) -> list[PlannerEvaluationItem]:
    """Load and validate planner benchmark items from JSON."""
    return [
        PlannerEvaluationItem.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def summarize_results(
    results: list[tuple[PlannerEvaluationRecord, PlannerJudgeEvaluation]],
) -> list[dict[str, str | int | float]]:
    """Calculate judge pass rates per planner approach."""
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
