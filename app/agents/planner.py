"""Structured planning agent for FoodMind multi-agent workflows."""

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.settings import get_settings


class AgentName(StrEnum):
    """Specialist agents available to the orchestrator."""

    FOOD_SEARCH = "food_search"
    NUTRITION_ANALYSIS = "nutrition_analysis"
    PRODUCT_COMPARISON = "product_comparison"
    FOOD_RECOMMENDATION = "food_recommendation"


class DelegationTask(BaseModel):
    """Structured objective delegated to one specialist agent."""

    objective: str = Field(min_length=1)
    context: str | None = None
    required_fields: list[str] = Field(default_factory=list)


class PlannedTask(BaseModel):
    """One node in the orchestrator execution graph."""

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    agent: AgentName
    task: DelegationTask
    depends_on: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """Validated directed acyclic graph of specialist work."""

    tasks: list[PlannedTask] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_dependencies(self) -> "ExecutionPlan":
        """Reject duplicate IDs, unknown dependencies, and dependency cycles."""
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Execution plan task IDs must be unique")
        known = set(task_ids)
        for task in self.tasks:
            unknown = set(task.depends_on) - known
            if unknown:
                raise ValueError(f"Unknown task dependencies: {sorted(unknown)}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            """Visit one task while checking for cycles."""
            if task_id in visiting:
                raise ValueError("Execution plan dependencies must be acyclic")
            if task_id in visited:
                return
            visiting.add(task_id)
            task = next(item for item in self.tasks if item.id == task_id)
            for dependency in task.depends_on:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        return self


@dataclass
class FoodMindPlanner:
    """Convert a natural-language request into a validated execution plan."""

    instructions: str | None = None
    agent: Agent[None, ExecutionPlan] = field(init=False)

    def __post_init__(self) -> None:
        """Create the structured-output planning agent."""
        settings = get_settings()
        model = settings.OPENAI_MODEL
        if settings.OPENAI_API_KEY:
            model = OpenAIChatModel(
                model_name=settings.OPENAI_MODEL.removeprefix("openai:"),
                provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
            )
        self.agent = Agent(
            model,
            output_type=ExecutionPlan,
            instructions=(
                "You are the FoodMind workflow planner. Select only the specialist "
                "agents needed for the request. Use unique snake_case task IDs. "
                "Tasks without dependencies can run in parallel. Add dependencies "
                "when a task needs an earlier agent's output. Put prior results in "
                "context requirements and specify required fields. Never answer the "
                "user; return only an execution plan. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=not bool(settings.OPENAI_API_KEY),
        )

    async def plan(self, prompt: str) -> AgentRunResult[ExecutionPlan]:
        """Create a typed execution plan for a user request."""
        return await self.agent.run(prompt)
