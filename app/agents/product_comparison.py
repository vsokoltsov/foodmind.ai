"""PydanticAI agent for comparing packaged food products."""

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agents.food_search import FoodSearchDependencies
from app.aggregates import BrandedFood, OpenFoodFactsProduct
from app.repositories.queries import BrandedFoodQuery, OpenFoodFactsQuery
from app.settings import get_settings


class ProductComparisonRequest(BaseModel):
    """Validated comparison criteria supplied to the comparison tool."""

    products: list[str] = Field(
        min_length=2,
        max_length=10,
        description="Product names or barcodes to compare",
    )
    criteria: list[str] = Field(
        default_factory=lambda: ["protein", "fiber"],
        min_length=1,
        description="Nutrients or product attributes to compare",
    )
    rank_by: str | None = Field(
        default=None,
        description="Criterion used to rank products, such as protein or fiber",
    )
    brand: str | None = None


class ComparisonProduct(BaseModel):
    """Comparable product facts gathered from one source."""

    id: str
    label: str
    source: str
    barcode: str | None = None
    nutrients: dict[str, float | None] = Field(default_factory=dict)
    ingredients: str | None = None
    allergens: str | None = None


class ProductComparisonResult(BaseModel):
    """Products and ranking returned by the comparison tool."""

    products: list[ComparisonProduct]
    ranked_ids: list[str] = Field(default_factory=list)
    compared_criteria: list[str] = Field(default_factory=list)


class ProductComparisonAnswer(BaseModel):
    """Typed natural-language response from the comparison agent."""

    answer: str
    comparison: ProductComparisonResult | None = None


@dataclass
class ProductComparisonAgent:
    """Compare branded and Open Food Facts products using repository tools."""

    instructions: str | None = None
    agent: Agent[FoodSearchDependencies, ProductComparisonAnswer] = field(
        init=False
    )

    def __post_init__(self) -> None:
        """Create the configured PydanticAI agent and register its tool."""
        settings = get_settings()
        model = settings.OPENAI_MODEL
        if settings.OPENAI_API_KEY:
            model = OpenAIChatModel(
                model_name=settings.OPENAI_MODEL.removeprefix("openai:"),
                provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
            )
        self.agent = Agent(
            model,
            deps_type=FoodSearchDependencies,
            output_type=ProductComparisonAnswer,
            instructions=(
                "You compare packaged food products. Always call compare_products "
                "before answering. Discuss only returned facts, show nutrient, "
                "ingredient and allergen differences, and explain rankings. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=not bool(settings.OPENAI_API_KEY),
        )
        self.agent.tool(self.compare_products)

    async def run(
        self, prompt: str, *, deps: FoodSearchDependencies
    ) -> AgentRunResult[ProductComparisonAnswer]:
        """Run the comparison agent with request-scoped repositories."""
        return await self.agent.run(prompt, deps=deps)

    async def compare_products(
        self,
        ctx: RunContext[FoodSearchDependencies],
        request: ProductComparisonRequest,
    ) -> ProductComparisonResult:
        """Look up products, collect comparison facts, and optionally rank them."""
        products = await asyncio.gather(
            *(
                self._lookup_product(ctx, value, request.brand, request.criteria)
                for value in request.products
            )
        )
        found = [product for product in products if product is not None]
        ranked = self._rank(found, request.rank_by)
        return ProductComparisonResult(
            products=found,
            ranked_ids=[product.id for product in ranked],
            compared_criteria=request.criteria,
        )

    async def _lookup_product(
        self,
        ctx: RunContext[FoodSearchDependencies],
        value: str,
        brand: str | None,
        criteria: list[str],
    ) -> ComparisonProduct | None:
        """Search both product repositories for one barcode or product name."""
        barcode = value if value.isdigit() else None
        off_query = OpenFoodFactsQuery(text=None if barcode else value, barcode=barcode)
        usda_query = BrandedFoodQuery(text=None if barcode else value, brand=brand, barcode=barcode)
        off_products, usda_products = await asyncio.gather(
            ctx.deps.openfoodfacts.search(off_query),
            ctx.deps.usda.search_branded(usda_query),
        )
        if usda_products:
            return self._from_usda(usda_products[0], criteria)
        if off_products:
            return self._from_openfoodfacts(off_products[0], criteria)
        return None

    @staticmethod
    def _from_usda(food: BrandedFood, criteria: list[str]) -> ComparisonProduct:
        """Convert a USDA branded aggregate into comparable facts."""
        nutrients = {
            nutrient.name: ProductComparisonAgent._normalize(nutrient.amount, nutrient.unit)
            for nutrient in food.nutrients
            if ProductComparisonAgent._matches(nutrient.name, criteria)
        }
        return ComparisonProduct(
            id=food.id,
            label=food.label,
            source=food.source,
            barcode=food.gtin_upc,
            nutrients=nutrients,
            ingredients=food.ingredients,
        )

    @staticmethod
    def _from_openfoodfacts(
        product: OpenFoodFactsProduct, criteria: list[str]
    ) -> ComparisonProduct:
        """Convert an Open Food Facts aggregate into comparable facts."""
        nutrients: dict[str, float | None] = {}
        for key, value in product.nutriments.items():
            if key.endswith("_100g") and isinstance(value, (int, float)):
                name = key.removesuffix("_100g")
                if ProductComparisonAgent._matches(name, criteria):
                    nutrients[name] = float(value)
        return ComparisonProduct(
            id=product.id,
            label=product.label,
            source=product.source,
            barcode=product.code,
            nutrients=nutrients,
            ingredients=product.ingredients,
            allergens=product.allergens,
        )

    @staticmethod
    def _normalize(amount: float | None, unit: str) -> float | None:
        """Normalize nutrient mass values to grams."""
        if amount is None:
            return None
        match unit.casefold():
            case "mg":
                return amount / 1000
            case "µg" | "ug" | "mcg":
                return amount / 1_000_000
            case _:
                return amount

    @staticmethod
    def _matches(name: str, criteria: list[str]) -> bool:
        """Match a nutrient name or Open Food Facts key to a criterion."""
        lowered = name.casefold().replace("_", " ")
        return any(term.casefold() in lowered for term in criteria)

    @staticmethod
    def _rank(
        products: list[ComparisonProduct], rank_by: str | None
    ) -> list[ComparisonProduct]:
        """Rank products by descending numeric nutrient value when requested."""
        if not rank_by:
            return products
        criterion = rank_by.casefold()

        def value(product: ComparisonProduct) -> float | None:
            """Find a nutrient value without depending on source casing."""
            for name, amount in product.nutrients.items():
                if name.casefold() == criterion or criterion in name.casefold():
                    return amount
            return None

        return sorted(
            products,
            key=lambda product: (
                value(product) is not None,
                value(product) or float("-inf"),
            ),
            reverse=True,
        )
