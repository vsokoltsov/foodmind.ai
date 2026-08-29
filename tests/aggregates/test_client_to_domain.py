from app.aggregates import (
    FoundationFood as FoundationFoodAggregate,
    OpenFoodFactsProduct as OpenFoodFactsAggregate,
)
from app.clients.openfoodfacts.models import OpenFoodFactsProduct
from app.clients.usda_fdc.models import (
    FoodCategory,
    FoodNutrient,
    FoundationFood,
    Nutrient,
)

def test_openfoodfacts_client_model_converts_to_domain() -> None:
    product = OpenFoodFactsProduct(code="123", product_name="Soup")

    domain = product.to_domain()

    assert isinstance(domain, OpenFoodFactsAggregate)
    assert domain.id == "openfoodfacts:123"
    assert domain.label == "Soup"


def test_usda_client_model_converts_to_domain() -> None:
    food = FoundationFood(
        food_class="FinalFood",
        description="Tomato soup",
        food_nutrients=[
            FoodNutrient(
                type="FoodNutrient",
                id=1,
                nutrient=Nutrient(
                    id=1008,
                    number="208",
                    name="Energy",
                    unit_name="kcal",
                ),
                amount=42,
            )
        ],
        food_attributes=[],
        food_category=FoodCategory(description="Soups"),
        is_historical_reference=False,
        ndb_number=1,
        data_type="Foundation",
        fdc_id=42,
        publication_date="1/1/2026",
    )

    domain = food.to_domain()

    assert isinstance(domain, FoundationFoodAggregate)
    assert domain.id == "usda-fdc:42"
    assert domain.nutrients[0].unit == "kcal"
