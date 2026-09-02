"""PydanticAI agent for searching and comparing USDA nutrition data."""

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, RunContext

from app.aggregates import BrandedFood, FoundationFood, Nutrition
from app.agents.foodmind import _create_model
from app.agents.food_search import FoodSearchDependencies
from app.repositories.queries import BrandedFoodQuery, USDAFoodQuery
from app.settings import get_settings


class USDAFoodSource(StrEnum):
    """USDA catalog to use for a nutrition lookup."""

    FOUNDATION = "foundation"
    BRANDED = "branded"


class NutritionAnalysisRequest(BaseModel):
    """Validated arguments for a nutrition analysis tool."""

    food: str = Field(min_length=1, description="Food name or product description")
    nutrients: list[str] = Field(
        default_factory=lambda: ["protein", "fiber"],
        min_length=1,
        description="Nutrient names to extract",
    )
    source: USDAFoodSource | None = None
    brand: str | None = None
    category: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class NutritionValue(BaseModel):
    """One normalized nutrient measurement per 100 grams of food."""

    name: str
    amount: float | None
    unit: str


class NutritionFoodResult(BaseModel):
    """Food identity and requested nutrient values returned by the tool."""

    id: str
    label: str
    source: str
    nutrients: list[NutritionValue]


class NutritionAnalysisAnswer(BaseModel):
    """Typed natural-language response returned by the nutrition agent."""

    answer: str
    foods: list[NutritionFoodResult] = Field(default_factory=list)


@dataclass
class NutritionAnalysisAgent:
    """Analyze USDA nutrients using repository-backed PydanticAI tools."""

    instructions: str | None = None
    agent: Agent[FoodSearchDependencies, NutritionAnalysisAnswer] = field(
        init=False
    )

    def __post_init__(self) -> None:
        """Create the configured PydanticAI agent and register its tool."""
        settings = get_settings()
        model: Any = _create_model() if settings.OPENAI_API_KEY else settings.OPENAI_MODEL
        self.agent = Agent(
            model,
            deps_type=FoodSearchDependencies,
            output_type=NutritionAnalysisAnswer,
            instructions=(
                "You are a nutrition analysis assistant. Always use the "
                "analyze_nutrition tool before answering. Report only returned "
                "USDA values, preserve the units, and state when evidence is "
                "missing. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=not bool(settings.OPENAI_API_KEY),
        )
        self.agent.tool(self.analyze_nutrition)

    async def run(
        self, prompt: str, *, deps: FoodSearchDependencies
    ) -> AgentRunResult[NutritionAnalysisAnswer]:
        """Run the nutrition agent with request-scoped repositories."""
        return await self.agent.run(prompt, deps=deps)

    async def analyze_nutrition(
        self,
        ctx: RunContext[FoodSearchDependencies],
        request: NutritionAnalysisRequest,
    ) -> list[NutritionFoodResult]:
        """Find USDA foods and extract the requested normalized nutrients."""
        match request.source:
            case USDAFoodSource.FOUNDATION:
                groups = [
                    await ctx.deps.usda.search_foundations(
                        USDAFoodQuery(text=request.food, category=request.category, limit=request.limit)
                    )
                ]
            case USDAFoodSource.BRANDED:
                groups = [
                    await ctx.deps.usda.search_branded(
                        BrandedFoodQuery(
                            text=request.food,
                            category=request.category,
                            brand=request.brand,
                            limit=request.limit,
                        )
                    )
                ]
            case None:
                groups = list(
                    await asyncio.gather(
                        ctx.deps.usda.search_foundations(
                            USDAFoodQuery(text=request.food, category=request.category, limit=request.limit)
                        ),
                        ctx.deps.usda.search_branded(
                            BrandedFoodQuery(
                                text=request.food,
                                category=request.category,
                                brand=request.brand,
                                limit=request.limit,
                            )
                        ),
                    )
                )
        foods = [food for group in groups for food in group][: request.limit]
        return [self._food_result(food, request.nutrients) for food in foods]

    @classmethod
    def _food_result(
        cls, food: FoundationFood | BrandedFood, requested: list[str]
    ) -> NutritionFoodResult:
        """Convert one USDA aggregate to a source-neutral result."""
        return NutritionFoodResult(
            id=food.id,
            label=food.label,
            source=food.source,
            nutrients=[
                cls._normalize(nutrient)
                for nutrient in food.nutrients
                if cls._matches(nutrient.name, requested)
            ],
        )

    @staticmethod
    def _matches(name: str, requested: list[str]) -> bool:
        """Match nutrient names using case-insensitive substring matching."""
        lowered = name.casefold()
        return any(term.casefold() in lowered for term in requested)

    @staticmethod
    def _normalize(nutrient: Nutrition) -> NutritionValue:
        """Normalize mass units to grams while preserving energy units."""
        unit = nutrient.unit.casefold()
        amount = nutrient.amount
        if amount is not None and unit == "mg":
            amount, unit = amount / 1000, "g"
        elif amount is not None and unit in {"µg", "ug", "mcg"}:
            amount, unit = amount / 1_000_000, "g"
        return NutritionValue(name=nutrient.name, amount=amount, unit=unit)


def create_nutrition_analysis_agent() -> NutritionAnalysisAgent:
    """Create a configured nutrition analysis agent."""
    return NutritionAnalysisAgent()
