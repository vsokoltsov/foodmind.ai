"""Dependency-aware execution of FoodMind specialist plans."""

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.agents.food_recommendation import FoodRecommendationAnswer
from app.agents.execution_state import ExecutionState
from app.agents.food_search import FoodSearchAnswer
from app.agents.nutrition_analysis import NutritionAnalysisAnswer
from app.agents.orchestrator import OrchestratorDependencies
from app.agents.planner import AgentName, ExecutionPlan, PlannedTask
from app.agents.product_comparison import ProductComparisonAnswer


AgentOutput = (
    FoodSearchAnswer
    | NutritionAnalysisAnswer
    | ProductComparisonAnswer
    | FoodRecommendationAnswer
)


class TaskExecution(BaseModel):
    """Result of one planned specialist task."""

    task_id: str
    agent: AgentName
    output: AgentOutput | None = None
    error: str | None = None
    cached: bool = False


class ExecutionReport(BaseModel):
    """Partial-tolerant result of executing a complete plan."""

    tasks: list[TaskExecution] = Field(default_factory=list)
    execution_state: ExecutionState | None = None

    @property
    def successful(self) -> list[TaskExecution]:
        """Return tasks that produced specialist output."""
        return [task for task in self.tasks if task.output is not None]


@dataclass
class PlanExecutor:
    """Execute a validated plan with bounded parallelism and caching."""

    max_total_calls: int = 8
    max_calls_per_agent: int = 3
    task_timeout_seconds: float = 120.0
    _cache: dict[tuple[AgentName, str], AgentOutput] = field(default_factory=dict)

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        prompt: str,
        dependencies: OrchestratorDependencies,
    ) -> ExecutionReport:
        """Execute all plan tasks respecting dependencies.

        Independent ready tasks run concurrently. A task may repeat an agent when
        its objective or context differs; identical requests are served from the
        executor cache. Failed tasks are reported without discarding successful
        results, while dependent tasks are marked as blocked.
        """
        dependencies.reset_budget()
        dependencies.max_total_calls = self.max_total_calls
        dependencies.max_calls_per_agent = self.max_calls_per_agent
        dependencies.original_prompt = prompt
        dependencies.execution_state = ExecutionState(
            original_query=prompt, rewritten_query=prompt
        )
        by_id = {task.id: task for task in plan.tasks}
        completed: dict[str, TaskExecution] = {}
        pending = set(by_id)

        while pending:
            blocked = [
                by_id[task_id]
                for task_id in pending
                if all(dependency in completed for dependency in by_id[task_id].depends_on)
                and any(completed[dependency].error for dependency in by_id[task_id].depends_on)
            ]
            for task in blocked:
                completed[task.id] = TaskExecution(
                    task_id=task.id,
                    agent=task.agent,
                    error="Blocked by a failed dependency",
                )
                if dependencies.execution_state is not None:
                    dependencies.execution_state.record_error(
                        task.id, ValueError("Blocked by a failed dependency")
                    )
                pending.remove(task.id)
            if not pending:
                break
            ready = [
                by_id[task_id]
                for task_id in pending
                if all(
                    dependency in completed
                    and completed[dependency].output is not None
                    for dependency in by_id[task_id].depends_on
                )
            ]
            if not ready:
                for task_id in pending:
                    completed[task_id] = TaskExecution(
                        task_id=task_id,
                        agent=by_id[task_id].agent,
                        error="Blocked by a failed or unresolved dependency",
                    )
                    if dependencies.execution_state is not None:
                        dependencies.execution_state.record_error(
                            task_id, ValueError("Blocked by a failed or unresolved dependency")
                        )
                break
            results = await asyncio.gather(
                *(self._execute_task(task, completed, dependencies) for task in ready),
                return_exceptions=False,
            )
            for result in results:
                completed[result.task_id] = result
                pending.remove(result.task_id)

        return ExecutionReport(
            tasks=[completed[task.id] for task in plan.tasks],
            execution_state=dependencies.execution_state,
        )

    async def _execute_task(
        self,
        task: PlannedTask,
        completed: dict[str, TaskExecution],
        dependencies: OrchestratorDependencies,
    ) -> TaskExecution:
        """Execute one task after its dependencies have completed."""
        context = self._context(task, completed)
        cache_key = (task.agent, task.task.objective + "\n" + context)
        cached = self._cache.get(cache_key)
        if cached is not None:
            step_key = f"{task.id}:{task.agent.value}"
            if dependencies.execution_state is not None:
                dependencies.execution_state.select_agent(task.agent.value)
                dependencies.execution_state.complete_step(step_key, cached)
            return TaskExecution(
                task_id=task.id, agent=task.agent, output=cached, cached=True
            )
        try:
            step_key = f"{task.id}:{task.agent.value}"
            dependencies.authorize(task.agent.value, step_key)
            result = await asyncio.wait_for(
                self._call_agent(task.agent, self._prompt(task, context), dependencies),
                timeout=self.task_timeout_seconds,
            )
            self._cache[cache_key] = result
            if dependencies.execution_state is not None:
                dependencies.execution_state.complete_step(step_key, result)
            return TaskExecution(task_id=task.id, agent=task.agent, output=result)
        except Exception as error:
            if dependencies.execution_state is not None:
                dependencies.execution_state.record_error(step_key, error)
            return TaskExecution(task_id=task.id, agent=task.agent, error=str(error))

    async def _call_agent(
        self, agent: AgentName, prompt: str, dependencies: OrchestratorDependencies
    ) -> AgentOutput:
        """Dispatch one task to its typed specialist agent."""
        match agent:
            case AgentName.FOOD_SEARCH:
                return (await dependencies.food_search.run(prompt, deps=dependencies.repositories)).output
            case AgentName.NUTRITION_ANALYSIS:
                return (await dependencies.nutrition_analysis.run(prompt, deps=dependencies.repositories)).output
            case AgentName.PRODUCT_COMPARISON:
                return (await dependencies.product_comparison.run(prompt, deps=dependencies.repositories)).output
            case AgentName.FOOD_RECOMMENDATION:
                return (await dependencies.food_recommendation.run(prompt, deps=dependencies.repositories)).output

    @staticmethod
    def _prompt(task: PlannedTask, context: str) -> str:
        """Render a specialist prompt from the structured task and context."""
        prompt = task.task.objective
        if task.task.context:
            prompt += f"\n\nTask context:\n{task.task.context}"
        if context:
            prompt += f"\n\nCompleted dependency results:\n{context}"
        if task.task.required_fields:
            prompt += "\n\nRequired fields: " + ", ".join(task.task.required_fields)
        return prompt

    @staticmethod
    def _context(task: PlannedTask, completed: dict[str, TaskExecution]) -> str:
        """Serialize successful dependency outputs for downstream tasks."""
        values = []
        for dependency in task.depends_on:
            result = completed[dependency]
            if result.output is not None:
                values.append(f"{dependency}: {result.output.model_dump_json()}")
        return "\n".join(values)
