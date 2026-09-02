"""LLM-as-judge evaluation for the FoodMind orchestrator."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded

from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import FoodMindOrchestrator, OrchestratorDependencies


class OrchestratorApproach(StrEnum):
    """Prompting strategies compared by the orchestrator benchmark."""

    DIRECT = "direct"
    PLAN_FIRST = "plan_first"


class OrchestratorEvaluationItem(BaseModel):
    """One orchestration question and its expected rubric."""

    question: str
    reference_answer: str


class OrchestratorEvaluationRecord(BaseModel):
    """Generated orchestrator answer submitted to the judge."""

    approach: OrchestratorApproach
    question: str
    reference_answer: str
    agent_answer: str


class OrchestratorJudgeEvaluation(BaseModel):
    """Structured quality decision from the judge model."""

    score: Literal["good", "bad"]
    reasoning: str = Field(description="Concise explanation for the score")


class OrchestratorJudge:
    """Judge multi-agent answers against reference rubrics."""

    def __init__(self, model: Any) -> None:
        """Create a structured-output judge agent."""
        self.agent: Agent[None, OrchestratorJudgeEvaluation] = Agent(
            model,
            output_type=OrchestratorJudgeEvaluation,
            instructions=(
                "Evaluate whether the orchestrator selected appropriate experts, "
                "combined their evidence correctly, and answered the question "
                "without unsupported claims."
            ),
        )

    async def evaluate(
        self, record: OrchestratorEvaluationRecord
    ) -> OrchestratorJudgeEvaluation:
        """Evaluate one orchestrator answer."""
        result = await self.agent.run(
            f"Question:\n{record.question}\n\n"
            f"Reference rubric:\n{record.reference_answer}\n\n"
            f"Agent answer ({record.approach.value}):\n{record.agent_answer}"
        )
        return result.output


@dataclass
class OrchestratorEvaluationRunner:
    """Generate and judge answers for multiple orchestration approaches."""

    repositories: FoodSearchDependencies
    judge: OrchestratorJudge

    async def run(
        self,
        items: list[OrchestratorEvaluationItem],
        approaches: list[OrchestratorApproach],
    ) -> list[tuple[OrchestratorEvaluationRecord, OrchestratorJudgeEvaluation]]:
        """Run every benchmark question through every approach."""
        if len(approaches) < 2:
            raise ValueError("Orchestrator evaluation requires two approaches")
        results = []
        for approach in approaches:
            instructions = {
                OrchestratorApproach.DIRECT: "Delegate only the work needed and answer directly.",
                OrchestratorApproach.PLAN_FIRST: (
                    "First determine which specialist agents are required, then "
                    "delegate and synthesize their evidence."
                ),
            }[approach]
            orchestrator = FoodMindOrchestrator(instructions=instructions)
            for item in items:
                dependencies = OrchestratorDependencies.from_repositories(self.repositories)
                try:
                    response = await orchestrator.run(
                        item.question,
                        deps=dependencies,
                        usage_limits=UsageLimits(request_limit=16, tool_calls_limit=6),
                    )
                    answer = response.output.answer
                except (UsageLimitExceeded, ValueError) as exc:
                    answer = f"Evaluation stopped before a final answer: {exc}"
                record = OrchestratorEvaluationRecord(
                    approach=approach,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    agent_answer=answer,
                )
                results.append((record, await self.judge.evaluate(record)))
        return results


def load_dataset(path: Path) -> list[OrchestratorEvaluationItem]:
    """Load and validate orchestrator benchmark items from JSON."""
    return [
        OrchestratorEvaluationItem.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def summarize_results(
    results: list[tuple[OrchestratorEvaluationRecord, OrchestratorJudgeEvaluation]],
) -> list[dict[str, str | int | float]]:
    """Calculate judge pass rates per orchestration approach."""
    summary = []
    for approach in sorted({record.approach for record, _ in results}, key=str):
        rows = [item for item in results if item[0].approach == approach]
        good = sum(evaluation.score == "good" for _, evaluation in rows)
        summary.append(
            {"approach": approach.value, "total": len(rows), "good": good, "good_rate": good / len(rows) if rows else 0.0}
        )
    return sorted(summary, key=lambda row: (row["good_rate"], row["good"]), reverse=True)
