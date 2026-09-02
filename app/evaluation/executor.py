"""LLM-as-judge evaluation for the dependency-aware plan executor."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.executor import ExecutionReport, PlanExecutor
from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies
from app.agents.planner import AgentName, DelegationTask, ExecutionPlan, PlannedTask


class ExecutorApproach(StrEnum):
    """Execution strategies compared by the benchmark."""

    MINIMAL = "minimal"
    EVIDENCE_RICH = "evidence_rich"


class ExecutorEvaluationItem(BaseModel):
    """One executor question and expected behavior rubric."""

    question: str
    reference_answer: str


class ExecutorEvaluationRecord(BaseModel):
    """Execution report submitted to the judge."""

    approach: ExecutorApproach
    question: str
    reference_answer: str
    report: ExecutionReport


class ExecutorJudgeEvaluation(BaseModel):
    """Structured quality decision from the executor judge."""

    score: Literal["good", "bad"]
    reasoning: str = Field(description="Concise explanation for the score")


class ExecutorJudge:
    """Judge execution reports against expected workflow behavior."""

    def __init__(self, model: Any) -> None:
        """Create a structured-output judge."""
        self.agent: Agent[None, ExecutorJudgeEvaluation] = Agent(
            model,
            output_type=ExecutorJudgeEvaluation,
            instructions=(
                "Evaluate whether the execution report contains relevant specialist "
                "evidence for the question, respects dependencies, and reports no "
                "unsupported conclusions."
            ),
        )

    async def evaluate(self, record: ExecutorEvaluationRecord) -> ExecutorJudgeEvaluation:
        """Evaluate one execution report."""
        result = await self.agent.run(
            f"Question:\n{record.question}\n\n"
            f"Reference rubric:\n{record.reference_answer}\n\n"
            f"Execution report ({record.approach.value}):\n"
            f"{record.report.model_dump_json()}"
        )
        return result.output


@dataclass
class ExecutorEvaluationRunner:
    """Execute and judge workflows for multiple execution approaches."""

    repositories: FoodSearchDependencies
    judge: ExecutorJudge

    @staticmethod
    def _plan(approach: ExecutorApproach, question: str) -> ExecutionPlan:
        """Build a representative dependency graph for one question."""
        required = ["id", "source", "protein"] if approach is ExecutorApproach.EVIDENCE_RICH else []
        return ExecutionPlan(
            tasks=[
                PlannedTask(
                    id="compare_products",
                    agent=AgentName.PRODUCT_COMPARISON,
                    task=DelegationTask(
                        objective="Find and compare the products in the user request.",
                        context=question,
                        required_fields=required,
                    ),
                ),
                PlannedTask(
                    id="analyze_nutrition",
                    agent=AgentName.NUTRITION_ANALYSIS,
                    task=DelegationTask(
                        objective="Analyze the requested nutrients for the products.",
                        context=question,
                        required_fields=["protein", "fiber"],
                    ),
                    depends_on=["compare_products"],
                ),
            ]
        )

    async def run(
        self,
        items: list[ExecutorEvaluationItem],
        approaches: list[ExecutorApproach],
    ) -> list[tuple[ExecutorEvaluationRecord, ExecutorJudgeEvaluation]]:
        """Run every question through every execution approach."""
        if len(approaches) < 2:
            raise ValueError("Executor evaluation requires two approaches")
        results = []
        for approach in approaches:
            for item in items:
                dependencies = OrchestratorDependencies.from_repositories(self.repositories)
                report = await PlanExecutor().execute(
                    self._plan(approach, item.question),
                    prompt=item.question,
                    dependencies=dependencies,
                )
                record = ExecutorEvaluationRecord(
                    approach=approach,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    report=report,
                )
                results.append((record, await self.judge.evaluate(record)))
        return results


def load_dataset(path: Path) -> list[ExecutorEvaluationItem]:
    """Load executor evaluation questions from JSON."""
    return [
        ExecutorEvaluationItem.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def summarize_results(
    results: list[tuple[ExecutorEvaluationRecord, ExecutorJudgeEvaluation]],
) -> list[dict[str, str | int | float]]:
    """Calculate judge pass rates per execution approach."""
    summary = []
    for approach in sorted({record.approach for record, _ in results}, key=str):
        rows = [item for item in results if item[0].approach == approach]
        good = sum(evaluation.score == "good" for _, evaluation in rows)
        summary.append({"approach": approach.value, "total": len(rows), "good": good, "good_rate": good / len(rows) if rows else 0.0})
    return sorted(summary, key=lambda row: (row["good_rate"], row["good"]), reverse=True)
