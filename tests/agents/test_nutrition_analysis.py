"""Unit tests for the nutrition analysis agent tools."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.aggregates import BrandedFood, Nutrition
from app.agents.food_search import FoodSearchDependencies
from app.agents.nutrition_analysis import (
    NutritionAnalysisAgent,
    NutritionAnalysisRequest,
    USDAFoodSource,
)


def test_normalize_converts_mass_to_grams() -> None:
    """Milligram nutrient values are converted to grams."""
    value = NutritionAnalysisAgent._normalize(
        Nutrition(id=1, number="203", name="Protein", unit="mg", amount=250)
    )

    assert value.amount == 0.25
    assert value.unit == "g"


def test_analyze_nutrition_routes_branded_source() -> None:
    """A branded request uses the branded USDA repository query."""
    usda = SimpleNamespace(
        search_foundations=AsyncMock(return_value=[]),
        search_branded=AsyncMock(
            return_value=[
                BrandedFood(
                    id="usda-fdc:1",
                    label="Protein bar",
                    fdc_id=1,
                    category="Bars",
                    brand_owner="Example",
                    gtin_upc="1",
                    ingredients="Oats",
                    market_country="US",
                    publication_date="2026-01-01",
                    serving_size=40,
                    serving_size_unit="g",
                    nutrients=[
                        Nutrition(id=1, number="203", name="Protein", unit="g", amount=10)
                    ],
                )
            ]
        ),
    )
    deps = FoodSearchDependencies(
        wikidata=SimpleNamespace(), usda=usda, openfoodfacts=SimpleNamespace()
    )
    results = asyncio.run(
        NutritionAnalysisAgent().analyze_nutrition(
            SimpleNamespace(deps=deps),
            NutritionAnalysisRequest(
                food="protein bar", source=USDAFoodSource.BRANDED
            ),
        )
    )

    assert results[0].nutrients[0].name == "Protein"
    usda.search_branded.assert_awaited_once()
