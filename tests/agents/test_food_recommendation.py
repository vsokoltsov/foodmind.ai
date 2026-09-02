"""Unit tests for food recommendation filtering."""

from app.aggregates import BrandedFood, Nutrition
from app.agents.food_recommendation import (
    FoodRecommendationAgent,
    FoodRecommendationRequest,
    NutritionTarget,
)


def _food() -> BrandedFood:
    """Build a representative branded food aggregate."""
    return BrandedFood(
        id="usda-fdc:1",
        label="Cocoa protein bar",
        fdc_id=1,
        category="Bars",
        brand_owner="Example",
        gtin_upc="1",
        ingredients="Cocoa, oats",
        market_country="US",
        publication_date="2026-01-01",
        serving_size=40,
        serving_size_unit="g",
        nutrients=[Nutrition(id=1, number="203", name="Protein", unit="g", amount=10)],
    )


def test_candidate_passes_ingredient_and_nutrition_constraints() -> None:
    """Candidates must contain available ingredients and meet targets."""
    request = FoodRecommendationRequest(
        available_ingredients=["cocoa"],
        nutrition_targets=[NutritionTarget(nutrient="protein", minimum=8)],
    )

    assert FoodRecommendationAgent._passes(_food(), request)


def test_candidate_is_rejected_for_excluded_allergen() -> None:
    """An excluded allergen appearing in product facts removes the candidate."""
    request = FoodRecommendationRequest(allergens=["oats"])

    assert not FoodRecommendationAgent._passes(_food(), request)
