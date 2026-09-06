"""Low-latency, guarded multi-agent orchestrator for FoodMind queries."""

import asyncio
import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, UsageLimits
from app.agents.food_recommendation import (
    FoodRecommendationAgent,
    FoodRecommendationAnswer,
)
from app.agents.execution_state import ExecutionState
from app.agents.food_search import (
    FoodSearchAgent,
    FoodSearchAnswer,
    FoodSearchDependencies,
)
from app.agents.nutrition_analysis import (
    NutritionAnalysisAgent,
    NutritionAnalysisAnswer,
)
from app.agents.product_comparison import (
    ProductComparisonAgent,
    ProductComparisonAnswer,
)
from app.agents.query_rewriter import QueryRewriter
from app.aggregates.model_configuration import ModelRole
from app.agents.model_factory import ModelFactory
from app.agents.planner import AgentName, ExecutionPlan, FoodMindPlanner
from app.agents.router import FoodMindRouter, RouteKind
from app.observability import metrics
from app.observability.tracing import tracing
from app.settings import get_settings

if TYPE_CHECKING:
    from app.agents.executor import ExecutionReport, PlanExecutor


class OrchestratorAnswer(BaseModel):
    """Final answer returned after specialist delegation."""

    answer: str
    used_agents: list[str] = Field(default_factory=list)


class OrchestratorRunResult(BaseModel):
    """Minimal result wrapper shared by direct and planned execution paths."""

    output: OrchestratorAnswer


@dataclass
class OrchestratorDependencies:
    """Specialist agents and execution budget for one orchestrator run."""

    repositories: FoodSearchDependencies
    food_search: FoodSearchAgent
    nutrition_analysis: NutritionAnalysisAgent
    product_comparison: ProductComparisonAgent
    food_recommendation: FoodRecommendationAgent
    max_total_calls: int = 6
    max_calls_per_agent: int = 2
    calls: dict[str, int] = field(default_factory=dict)
    original_prompt: str | None = None
    execution_state: ExecutionState | None = None
    event_callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None

    async def emit(self, event: str, **data: Any) -> None:
        """Publish an observable execution event when a sink is configured."""
        if self.event_callback is not None:
            await self.event_callback(event, data)

    @classmethod
    def from_repositories(
        cls, repositories: FoodSearchDependencies
    ) -> "OrchestratorDependencies":
        """Create specialist agents over shared repository dependencies."""
        return cls(
            repositories=repositories,
            food_search=FoodSearchAgent(),
            nutrition_analysis=NutritionAnalysisAgent(),
            product_comparison=ProductComparisonAgent(),
            food_recommendation=FoodRecommendationAgent(),
        )

    def reset_budget(self, *, reset_state: bool = True) -> None:
        """Reset call counters before starting a new user request.

        Args:
            reset_state: Also discard the request's prompt and execution state.
                Executors pass ``False`` when they are continuing the state
                initialized by the orchestrator's rewrite stage.
        """
        self.calls.clear()
        if reset_state:
            self.original_prompt = None
            self.execution_state = None

    def authorize(self, agent_name: str, step_key: str | None = None) -> None:
        """Enforce total and per-agent delegation limits."""
        total = sum(self.calls.values())
        current = self.calls.get(agent_name, 0)
        if total >= self.max_total_calls:
            raise ValueError("Orchestrator delegation budget exhausted")
        if current >= self.max_calls_per_agent:
            raise ValueError(f"Delegation limit reached for {agent_name}")
        if self.execution_state is not None:
            self.execution_state.select_agent(agent_name)
            if step_key is not None:
                self.execution_state.start_step(step_key)
        self.calls[agent_name] = current + 1


@dataclass
class FoodMindOrchestrator:
    """Route a user request to one or more guarded specialist agents."""

    instructions: str | None = None
    planner: FoodMindPlanner = field(init=False)
    query_rewriter: QueryRewriter = field(init=False)
    router: FoodMindRouter = field(init=False)
    executor: "PlanExecutor" = field(init=False)
    synthesizer: Agent[None, OrchestratorAnswer] = field(init=False)
    food_search: FoodSearchAgent = field(init=False)
    nutrition_analysis: NutritionAnalysisAgent = field(init=False)
    product_comparison: ProductComparisonAgent = field(init=False)
    food_recommendation: FoodRecommendationAgent = field(init=False)

    def __post_init__(self) -> None:
        """Create the request router, plan executor, and final synthesizer."""
        settings = get_settings()
        self.query_rewriter = QueryRewriter()
        self.planner = FoodMindPlanner()
        self.router = FoodMindRouter()
        self.food_search = FoodSearchAgent()
        self.nutrition_analysis = NutritionAnalysisAgent()
        self.product_comparison = ProductComparisonAgent()
        self.food_recommendation = FoodRecommendationAgent()
        from app.agents.executor import PlanExecutor

        self.executor = PlanExecutor(
            task_timeout_seconds=settings.AGENT_TIMEOUT_SECONDS
        )
        factory = ModelFactory(settings)
        model = factory.build(ModelRole.SYNTHESIS)
        self.synthesizer = Agent(
            model,
            output_type=OrchestratorAnswer,
            instructions=(
                "You are the FoodMind answer synthesizer. Combine only the supplied "
                "specialist evidence into a concise, useful answer. Do not invent "
                "facts, mention missing evidence when relevant, and list the agents "
                "that supplied evidence. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=factory.defer_model_check(),
        )

    async def create_plan(self, prompt: str) -> AgentRunResult[ExecutionPlan]:
        """Create a structured plan before executing specialist tools."""
        return await asyncio.wait_for(
            self.planner.plan(prompt),
            timeout=get_settings().PLANNER_TIMEOUT_SECONDS,
        )

    async def run(
        self,
        prompt: str,
        *,
        deps: OrchestratorDependencies,
        usage_limits: UsageLimits | None = None,
    ) -> OrchestratorRunResult:
        """Run a direct specialist or a planned concurrent workflow."""
        run_started = perf_counter()
        self._bind_agents(deps)
        deps.reset_budget()
        deps.repositories.reset_request_cache()
        deps.original_prompt = prompt
        deps.execution_state = ExecutionState(original_query=prompt)
        rewrite_started = perf_counter()
        rewrite = await self.query_rewriter.rewrite(prompt)
        rewritten_prompt = rewrite.query
        deps.execution_state.rewritten_query = rewritten_prompt
        deps.execution_state.record_duration(
            "query_rewrite", (perf_counter() - rewrite_started) * 1000
        )
        await deps.emit(
            "query_rewritten",
            method=rewrite.method.value,
            query=rewritten_prompt,
        )
        metrics.record_stage(
            stage="query_rewrite",
            outcome="success",
            duration_seconds=perf_counter() - rewrite_started,
        )
        route = self.router.route(rewritten_prompt)
        route_name = "direct" if route.kind is RouteKind.DIRECT else "planned"
        try:
            if route.kind is RouteKind.DIRECT and route.agent is not None:
                result = await self._run_direct(
                    route.agent, rewritten_prompt, deps, usage_limits
                )
            else:
                planner_started = perf_counter()
                with tracing.span("foodmind.orchestrator.plan") as span:
                    try:
                        plan = await self.create_plan(rewritten_prompt)
                    except Exception as error:
                        span.set_attribute("foodmind.outcome", "error")
                        deps.execution_state.record_error("planner", error)
                        await deps.emit("planner_error", error=str(error))
                        metrics.record_stage(
                            stage="planner",
                            outcome="error",
                            duration_seconds=perf_counter() - planner_started,
                        )
                        raise
                    span.set_attribute("foodmind.outcome", "success")
                planner_duration = perf_counter() - planner_started
                deps.execution_state.record_duration("planner", planner_duration * 1000)
                metrics.record_stage(
                    stage="planner",
                    outcome="success",
                    duration_seconds=planner_duration,
                )
                execution_started = perf_counter()
                with tracing.span("foodmind.orchestrator.execute") as span:
                    report = await self.executor.execute(
                        plan.output, prompt=rewritten_prompt, dependencies=deps
                    )
                    span.set_attribute("foodmind.outcome", "success")
                metrics.record_stage(
                    stage="executor",
                    outcome="success",
                    duration_seconds=perf_counter() - execution_started,
                )
                result = await self._synthesize(prompt, report)
        except Exception:
            metrics.record_orchestrator_run(
                route=route_name,
                outcome="error",
                duration_seconds=perf_counter() - run_started,
            )
            raise
        metrics.record_orchestrator_run(
            route=route_name,
            outcome="success",
            duration_seconds=perf_counter() - run_started,
        )
        return result

    def _bind_agents(self, deps: OrchestratorDependencies) -> None:
        """Reuse process-scoped specialist agents with request-scoped repositories."""
        deps.food_search = self.food_search
        deps.nutrition_analysis = self.nutrition_analysis
        deps.product_comparison = self.product_comparison
        deps.food_recommendation = self.food_recommendation

    async def _run_direct(
        self,
        agent: AgentName,
        prompt: str,
        deps: OrchestratorDependencies,
        usage_limits: UsageLimits | None,
    ) -> OrchestratorRunResult:
        """Run one clear specialist request without planner or synthesis calls."""
        step_key = f"direct:{agent.value}"
        deps.authorize(agent.value, step_key)
        await deps.emit("agent_started", agent=agent.value, step=step_key)
        await deps.emit("tool_started", agent=agent.value, tool=self._tool_name(agent))
        started = perf_counter()
        try:
            with tracing.span(
                "foodmind.agent.execute", {"foodmind.agent": agent.value}
            ) as span:
                result = await asyncio.wait_for(
                    self._call_agent(agent, prompt, deps, usage_limits),
                    timeout=get_settings().AGENT_TIMEOUT_SECONDS,
                )
                span.set_attribute("foodmind.outcome", "success")
        except Exception as error:
            duration = perf_counter() - started
            if deps.execution_state is not None:
                deps.execution_state.record_error(step_key, error)
            metrics.record_agent_run(
                agent=agent.value,
                outcome="error",
                cached=False,
                duration_seconds=duration,
            )
            metrics.record_stage(
                stage="agent", outcome="error", duration_seconds=duration
            )
            metrics.record_tool_call(
                agent=agent.value,
                tool=self._tool_name(agent),
                outcome="error",
            )
            await deps.emit(
                "agent_error", agent=agent.value, step=step_key, error=str(error)
            )
            raise
        duration = perf_counter() - started
        if deps.execution_state is not None:
            deps.execution_state.complete_step(step_key, result)
            deps.execution_state.record_duration(step_key, duration * 1000)
        metrics.record_agent_run(
            agent=agent.value,
            outcome="success",
            cached=False,
            duration_seconds=duration,
        )
        metrics.record_stage(
            stage="agent", outcome="success", duration_seconds=duration
        )
        metrics.record_tool_call(
            agent=agent.value,
            tool=self._tool_name(agent),
            outcome="success",
        )
        await deps.emit(
            "tool_completed", agent=agent.value, tool=self._tool_name(agent)
        )
        await deps.emit("agent_completed", agent=agent.value, step=step_key)
        return OrchestratorRunResult(
            output=OrchestratorAnswer(answer=result.answer, used_agents=[agent.value])
        )

    async def _call_agent(
        self,
        agent: AgentName,
        prompt: str,
        deps: OrchestratorDependencies,
        usage_limits: UsageLimits | None,
    ) -> (
        FoodSearchAnswer
        | NutritionAnalysisAnswer
        | ProductComparisonAnswer
        | FoodRecommendationAnswer
    ):
        """Dispatch a direct specialist request to its typed agent."""
        match agent:
            case AgentName.FOOD_SEARCH:
                return (
                    await deps.food_search.run(prompt, deps=deps.repositories)
                ).output
            case AgentName.NUTRITION_ANALYSIS:
                return (
                    await deps.nutrition_analysis.run(
                        prompt, deps=deps.repositories, usage_limits=usage_limits
                    )
                ).output
            case AgentName.PRODUCT_COMPARISON:
                return (
                    await deps.product_comparison.run(prompt, deps=deps.repositories)
                ).output
            case AgentName.FOOD_RECOMMENDATION:
                return (
                    await deps.food_recommendation.run(prompt, deps=deps.repositories)
                ).output

    async def _synthesize(
        self, prompt: str, report: "ExecutionReport"
    ) -> OrchestratorRunResult:
        """Generate one response from compact successful specialist evidence."""
        successful = report.successful
        if not successful:
            raise ValueError("No specialist task completed successfully")
        if len(successful) == 1:
            task = successful[0]
            if task.output is None:
                raise ValueError("Successful task is missing an output")
            return OrchestratorRunResult(
                output=OrchestratorAnswer(
                    answer=task.output.answer,
                    used_agents=[task.agent.value],
                )
            )
        evidence = [
            {
                "agent": task.agent.value,
                "output": self._compact(task.output.model_dump(mode="json")),
            }
            for task in successful
            if task.output is not None
        ]
        started = perf_counter()
        settings = get_settings()
        model = ModelFactory(settings).name_for(ModelRole.SYNTHESIS)
        with tracing.span("foodmind.orchestrator.synthesis") as span:
            try:
                result = await asyncio.wait_for(
                    self.synthesizer.run(
                        f"User request:\n{prompt}\n\nSpecialist evidence:\n"
                        f"{json.dumps(evidence, ensure_ascii=False)}"
                    ),
                    timeout=settings.SYNTHESIS_TIMEOUT_SECONDS,
                )
            except Exception:
                span.set_attribute("foodmind.outcome", "error")
                duration = perf_counter() - started
                metrics.record_llm_failure(
                    component="synthesis", agent="synthesis", model=model
                )
                metrics.record_stage(
                    stage="synthesis", outcome="error", duration_seconds=duration
                )
                raise
            span.set_attribute("foodmind.outcome", "success")
            span.set_attribute("gen_ai.request.model", model.removeprefix("openai:"))
            span.set_attribute("gen_ai.usage.input_tokens", result.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", result.usage.output_tokens)
        duration = perf_counter() - started
        metrics.record_llm_usage(
            component="synthesis",
            agent="synthesis",
            model=model,
            usage=result.usage,
        )
        metrics.record_stage(
            stage="synthesis", outcome="success", duration_seconds=duration
        )
        output = result.output
        if report.execution_state is not None:
            report.execution_state.record_duration("synthesis", duration * 1000)
        output.used_agents = [task.agent.value for task in successful]
        return OrchestratorRunResult(output=output)

    @staticmethod
    def _tool_name(agent: AgentName) -> str:
        """Return the specialist's externally visible retrieval tool name."""
        return {
            AgentName.FOOD_SEARCH: "search_foods",
            AgentName.NUTRITION_ANALYSIS: "analyze_nutrition",
            AgentName.PRODUCT_COMPARISON: "compare_products",
            AgentName.FOOD_RECOMMENDATION: "recommend_foods",
        }[agent]

    @classmethod
    def _compact(cls, value: Any) -> Any:
        """Bound evidence size before it is sent to the synthesis model."""
        if isinstance(value, str):
            return value[:500]
        if isinstance(value, list):
            return [cls._compact(item) for item in value[:3]]
        if isinstance(value, dict):
            return {key: cls._compact(item) for key, item in list(value.items())[:12]}
        return value
