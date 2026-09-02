"""Guarded multi-agent orchestrator for FoodMind queries."""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, RunContext

from app.agents.food_recommendation import (
    FoodRecommendationAgent,
    FoodRecommendationAnswer,
)
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
from app.agents.foodmind import _create_model
from app.settings import get_settings


class OrchestratorAnswer(BaseModel):
    """Final answer returned after specialist delegation."""

    answer: str
    used_agents: list[str] = Field(default_factory=list)


class DelegationTask(BaseModel):
    """Structured task passed from the orchestrator to a specialist agent."""

    objective: str = Field(min_length=1, description="Specific work to perform")
    context: str | None = Field(
        default=None,
        description="Relevant user requirements or results from earlier agents",
    )
    required_fields: list[str] = Field(
        default_factory=list,
        description="Facts or fields the specialist must return",
    )


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

    def reset_budget(self) -> None:
        """Reset call counters before starting a new user request."""
        self.calls.clear()
        self.original_prompt = None

    def authorize(self, agent_name: str) -> None:
        """Enforce total and per-agent delegation limits."""
        total = sum(self.calls.values())
        current = self.calls.get(agent_name, 0)
        if total >= self.max_total_calls:
            raise ValueError("Orchestrator delegation budget exhausted")
        if current >= self.max_calls_per_agent:
            raise ValueError(f"Delegation limit reached for {agent_name}")
        self.calls[agent_name] = current + 1


@dataclass
class FoodMindOrchestrator:
    """Route a user request to one or more guarded specialist agents."""

    instructions: str | None = None
    agent: Agent[OrchestratorDependencies, OrchestratorAnswer] = field(init=False)

    def __post_init__(self) -> None:
        """Create the orchestrator and register specialist-agent tools."""
        settings = get_settings()
        model: Any = _create_model() if settings.OPENAI_API_KEY else settings.OPENAI_MODEL
        self.agent = Agent(
            model,
            deps_type=OrchestratorDependencies,
            output_type=OrchestratorAnswer,
            instructions=(
                "You are the FoodMind orchestrator. Delegate work to specialist "
                "agent tools when their expertise is needed. You may call several "
                "tools, but do not repeat an agent unnecessarily. Synthesize their "
                "returned evidence into one answer and never invent facts. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=not bool(settings.OPENAI_API_KEY),
        )
        self.agent.tool(self.run_food_search)
        self.agent.tool(self.run_nutrition_analysis)
        self.agent.tool(self.run_product_comparison)
        self.agent.tool(self.run_food_recommendation)

    async def run(
        self, prompt: str, *, deps: OrchestratorDependencies
    ) -> AgentRunResult[OrchestratorAnswer]:
        """Run one orchestrated request with a fresh delegation budget."""
        deps.reset_budget()
        deps.original_prompt = prompt
        return await self.agent.run(prompt, deps=deps)

    async def _delegate(
        self,
        ctx: RunContext[OrchestratorDependencies],
        name: str,
        call: Callable[[str], Awaitable[Any]],
        task: DelegationTask,
    ) -> Any:
        """Authorize and execute one specialist-agent call."""
        ctx.deps.authorize(name)
        prompt = task.objective
        if ctx.deps.original_prompt:
            prompt += f"\n\nOriginal user request:\n{ctx.deps.original_prompt}"
        if task.context:
            prompt += f"\n\nRelevant context:\n{task.context}"
        if task.required_fields:
            prompt += "\n\nRequired fields: " + ", ".join(task.required_fields)
        return await call(prompt)

    async def run_food_search(
        self, ctx: RunContext[OrchestratorDependencies], task: DelegationTask
    ) -> FoodSearchAnswer:
        """Delegate food discovery to the food-search agent."""
        result = await self._delegate(
            ctx,
            "food_search",
            lambda prompt: ctx.deps.food_search.run(prompt, deps=ctx.deps.repositories),
            task,
        )
        return result.output

    async def run_nutrition_analysis(
        self, ctx: RunContext[OrchestratorDependencies], task: DelegationTask
    ) -> NutritionAnalysisAnswer:
        """Delegate nutrient analysis to the nutrition agent."""
        result = await self._delegate(
            ctx,
            "nutrition_analysis",
            lambda prompt: ctx.deps.nutrition_analysis.run(
                prompt, deps=ctx.deps.repositories
            ),
            task,
        )
        return result.output

    async def run_product_comparison(
        self, ctx: RunContext[OrchestratorDependencies], task: DelegationTask
    ) -> ProductComparisonAnswer:
        """Delegate product comparison to the comparison agent."""
        result = await self._delegate(
            ctx,
            "product_comparison",
            lambda prompt: ctx.deps.product_comparison.run(
                prompt, deps=ctx.deps.repositories
            ),
            task,
        )
        return result.output

    async def run_food_recommendation(
        self, ctx: RunContext[OrchestratorDependencies], task: DelegationTask
    ) -> FoodRecommendationAnswer:
        """Delegate constrained recommendations to the recommendation agent."""
        result = await self._delegate(
            ctx,
            "food_recommendation",
            lambda prompt: ctx.deps.food_recommendation.run(
                prompt, deps=ctx.deps.repositories
            ),
            task,
        )
        return result.output


def create_orchestrator() -> FoodMindOrchestrator:
    """Create a configured FoodMind orchestrator."""
    return FoodMindOrchestrator()
