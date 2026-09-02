"""Unit tests for the product comparison agent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.aggregates import BrandedFood, Nutrition
from app.agents.food_search import FoodSearchDependencies
from app.agents.product_comparison import (
    ComparisonProduct,
    ProductComparisonAgent,
    ProductComparisonRequest,
)


def test_normalize_mass_to_grams() -> None:
    """Comparison nutrient values use grams for mass units."""
    assert ProductComparisonAgent._normalize(250, "mg") == 0.25


def test_rank_orders_products_by_selected_nutrient() -> None:
    """Ranking puts the product with the largest nutrient value first."""
    products = [
        ComparisonProduct(id="a", label="A", source="usda_fdc", nutrients={"protein": 5}),
        ComparisonProduct(id="b", label="B", source="usda_fdc", nutrients={"protein": 15}),
    ]

    ranked = ProductComparisonAgent._rank(products, "protein")

    assert [product.id for product in ranked] == ["b", "a"]


def test_compare_products_looks_up_barcodes_in_both_sources() -> None:
    """A barcode lookup concurrently queries USDA and Open Food Facts."""
    food = BrandedFood(
        id="usda-fdc:1",
        label="Bar",
        fdc_id=1,
        category="Bars",
        brand_owner="Example",
        gtin_upc="123",
        ingredients="Oats",
        market_country="US",
        publication_date="2026-01-01",
        serving_size=40,
        serving_size_unit="g",
        nutrients=[Nutrition(id=1, number="203", name="Protein", unit="g", amount=10)],
    )
    usda = SimpleNamespace(
        search_branded=AsyncMock(return_value=[food]),
        search_foundations=AsyncMock(return_value=[]),
    )
    off = SimpleNamespace(search=AsyncMock(return_value=[]))
    deps = FoodSearchDependencies(
        wikidata=SimpleNamespace(), usda=usda, openfoodfacts=off
    )

    result = asyncio.run(
        ProductComparisonAgent().compare_products(
            SimpleNamespace(deps=deps),
            ProductComparisonRequest(products=["123", "456"], criteria=["protein"]),
        )
    )

    assert result.products[0].barcode == "123"
    assert result.products[0].nutrients["Protein"] == 10
    assert {
        call.args[0].barcode for call in usda.search_branded.await_args_list
    } == {"123", "456"}
    assert {call.args[0].barcode for call in off.search.await_args_list} == {
        "123",
        "456",
    }
