"""PydanticAI agent for constraint-based food recommendations."""

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.aggregates import BrandedFood, FoodEntity, FoundationFood, OpenFoodFactsProduct
from app.agents.food_search import FoodSearchDependencies
from app.observability import metrics
from app.observability.tracing import tracing
from app.repositories.queries import BrandedFoodQuery, OpenFoodFactsQuery, USDAFoodQuery, WikidataFoodQuery
from app.settings import get_settings


class NutritionTarget(BaseModel):
    """Minimum nutrient target expressed in grams per 100 grams."""

    nutrient: str
    minimum: float = Field(ge=0)


class FoodRecommendationRequest(BaseModel):
    """Validated constraints supplied to the recommendation tool."""

    cuisine: str | None = None
    dietary_preferences: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    nutrition_targets: list[NutritionTarget] = Field(default_factory=list)
    available_ingredients: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)


class RecommendedFood(BaseModel):
    """Candidate food that passed recommendation constraints."""

    id: str
    label: str
    source: str
    description: str | None = None
    ingredients: str | None = None
    allergens: str | None = None
    nutrients: dict[str, float | None] = Field(default_factory=dict)


class FoodRecommendationAnswer(BaseModel):
    """Typed natural-language recommendation response."""

    answer: str
    recommendations: list[RecommendedFood] = Field(default_factory=list)


@dataclass
class FoodRecommendationAgent:
    """Recommend foods by searching and filtering the source repositories."""

    instructions: str | None = None
    agent: Agent[FoodSearchDependencies, FoodRecommendationAnswer] = field(
        init=False
    )

    def __post_init__(self) -> None:
        """Create the configured PydanticAI agent and register its tool."""
        settings = get_settings()
        model = settings.OPENAI_AGENT_MODEL or settings.OPENAI_MODEL
        if settings.OPENAI_API_KEY:
            model = OpenAIChatModel(
                model_name=model.removeprefix("openai:"),
                provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
            )
        self.agent = Agent(
            model,
            deps_type=FoodSearchDependencies,
            output_type=FoodRecommendationAnswer,
            instructions=(
                "You recommend foods from the catalog. Always call recommend_foods "
                "before answering. Respect every dietary preference, nutrition "
                "target, available ingredient, and allergen exclusion. Use only "
                "returned evidence and explain any unmet constraint. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=not bool(settings.OPENAI_API_KEY),
        )
        self.agent.tool(self.recommend_foods)

    async def run(
        self, prompt: str, *, deps: FoodSearchDependencies
    ) -> AgentRunResult[FoodRecommendationAnswer]:
        """Run the recommendation agent with request-scoped repositories."""
        settings = get_settings()
        model = settings.OPENAI_AGENT_MODEL or settings.OPENAI_MODEL
        with tracing.span(
            "foodmind.llm.agent", {"foodmind.agent": "food_recommendation"}
        ) as span:
            try:
                result = await self.agent.run(prompt, deps=deps)
            except Exception:
                span.set_attribute("foodmind.outcome", "error")
                metrics.record_llm_failure(
                    component="agent", agent="food_recommendation", model=model
                )
                raise
            span.set_attribute("foodmind.outcome", "success")
            span.set_attribute("gen_ai.request.model", model.removeprefix("openai:"))
            span.set_attribute("gen_ai.usage.input_tokens", result.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", result.usage.output_tokens)
        metrics.record_llm_usage(
            component="agent",
            agent="food_recommendation",
            model=model,
            usage=result.usage,
        )
        return result

    async def recommend_foods(
        self,
        ctx: RunContext[FoodSearchDependencies],
        request: FoodRecommendationRequest,
    ) -> list[RecommendedFood]:
        """Search source catalogs and return candidates passing all constraints."""
        text = " ".join(request.available_ingredients) or request.cuisine
        searches = []
        if request.cuisine:
            searches.append(
                ctx.deps.search_wikidata(
                    WikidataFoodQuery(text=text, limit=request.limit)
                )
            )
        if request.nutrition_targets:
            searches.append(
                ctx.deps.search_foundations(
                    USDAFoodQuery(text=text, limit=request.limit)
                )
            )
        if request.allergens or request.dietary_preferences or request.nutrition_targets:
            searches.extend(
                [
                    ctx.deps.search_branded(
                        BrandedFoodQuery(text=text, limit=request.limit)
                    ),
                    ctx.deps.search_openfoodfacts(
                        OpenFoodFactsQuery(text=text, limit=request.limit)
                    ),
                ]
            )
        if not searches:
            searches.append(
                ctx.deps.search_openfoodfacts(
                    OpenFoodFactsQuery(text=text, limit=request.limit)
                )
            )
        candidates = [food for group in await asyncio.gather(*searches) for food in group]
        recommendations = [
            self._candidate(food)
            for food in candidates
            if self._passes(food, request)
        ]
        return recommendations[: request.limit]

    @classmethod
    def _candidate(
        cls, food: FoodEntity | FoundationFood | BrandedFood | OpenFoodFactsProduct
    ) -> RecommendedFood:
        """Convert a domain food object into a recommendation candidate."""
        if isinstance(food, FoodEntity):
            return RecommendedFood(
                id=food.id, label=food.label, source="wikidata", description=food.description
            )
        if isinstance(food, OpenFoodFactsProduct):
            nutrients = {
                key.removesuffix("_100g"): float(value)
                for key, value in food.nutriments.items()
                if key.endswith("_100g") and isinstance(value, (int, float))
            }
            return RecommendedFood(
                id=food.id, label=food.label, source=food.source,
                description=food.description, ingredients=food.ingredients,
                allergens=food.allergens, nutrients=nutrients,
            )
        return RecommendedFood(
            id=food.id, label=food.label, source=food.source,
            description=food.description,
            ingredients=food.ingredients if isinstance(food, BrandedFood) else None,
            nutrients={
                nutrient.name: cls._normalize(nutrient.amount, nutrient.unit)
                for nutrient in food.nutrients
            },
        )

    @classmethod
    def _passes(
        cls,
        food: FoodEntity | FoundationFood | BrandedFood | OpenFoodFactsProduct,
        request: FoodRecommendationRequest,
    ) -> bool:
        """Apply cuisine, dietary, ingredient, nutrient, and allergen filters."""
        text = cls._food_text(food).casefold()
        if request.cuisine and request.cuisine.casefold() not in text:
            if not isinstance(food, FoodEntity) or not any(
                request.cuisine.casefold() in (item.label or "").casefold()
                for item in food.cuisines
            ):
                return False
        for ingredient in request.available_ingredients:
            if ingredient.casefold() not in text:
                return False
        for allergen in request.allergens:
            if allergen.casefold() in text:
                return False
        if any(pref.casefold() == "vegan" for pref in request.dietary_preferences):
            if any(term in text for term in ("meat", "milk", "cheese", "egg", "fish", "butter")):
                return False
        nutrients = cls._candidate(food).nutrients
        for target in request.nutrition_targets:
            value = next(
                (amount for name, amount in nutrients.items() if target.nutrient.casefold() in name.casefold()),
                None,
            )
            if value is None or value < target.minimum:
                return False
        return True

    @staticmethod
    def _food_text(
        food: FoodEntity | FoundationFood | BrandedFood | OpenFoodFactsProduct,
    ) -> str:
        """Build searchable text from names, descriptions, and ingredients."""
        values = [food.label, food.description or ""]
        if isinstance(food, FoodEntity):
            values.extend(item.label or "" for item in food.cuisines)
        elif isinstance(food, BrandedFood):
            values.append(food.ingredients)
        elif isinstance(food, OpenFoodFactsProduct):
            values.extend([food.ingredients or "", food.allergens or "", food.categories or ""])
        return " ".join(values)

    @staticmethod
    def _normalize(amount: float | None, unit: str) -> float | None:
        """Normalize mass values to grams."""
        if amount is None:
            return None
        match unit.casefold():
            case "mg":
                return amount / 1000
            case "µg" | "ug" | "mcg":
                return amount / 1_000_000
            case _:
                return amount
