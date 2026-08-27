import pytest
from elasticsearch import AsyncElasticsearch

from app.clients.usda_fdc.models import (
    BrandedFood,
    FoodCategory,
    FoodNutrient,
    FoundationFood,
    LabelNutrients,
    Nutrient,
)
from app.repositories.usda import USDARepository
from tests.repositories.conftest import get_document, run

pytestmark = pytest.mark.integration


@pytest.fixture
def food_nutrient() -> FoodNutrient:
    """Provide a representative USDA nutrient measurement."""
    return FoodNutrient(
        type="FoodNutrient",
        id=12345,
        nutrient=Nutrient(
            id=1008,
            number="208",
            name="Energy",
            unit_name="kcal",
        ),
        amount=166,
    )


@pytest.fixture
def foundation_food(food_nutrient: FoodNutrient) -> FoundationFood:
    """Provide a minimal complete USDA Foundation Food."""
    return FoundationFood(
        food_class="FinalFood",
        description="Hummus, prepared from chickpeas",
        food_nutrients=[food_nutrient],
        food_attributes=[],
        food_category=FoodCategory(
            id=16,
            description="Legumes and Legume Products",
        ),
        is_historical_reference=False,
        ndb_number=16158,
        data_type="Foundation",
        fdc_id=321358,
        publication_date="4/1/2019",
        scientific_name="Cicer arietinum",
    )


@pytest.fixture
def branded_food(food_nutrient: FoodNutrient) -> BrandedFood:
    """Provide a minimal complete USDA Branded Food."""
    return BrandedFood(
        food_class="Branded",
        description="Classic Hummus",
        short_description="Chickpea dip",
        food_nutrients=[food_nutrient],
        food_attributes=[],
        modified_date="5/1/2026",
        available_date="5/10/2026",
        market_country="United States",
        brand_owner="Example Foods Inc.",
        brand_name="Example",
        data_source="LI",
        branded_food_category="Dips and spreads",
        gtin_upc="012345678901",
        ingredients="CHICKPEAS, TAHINI, OLIVE OIL",
        serving_size=28,
        serving_size_unit="g",
        household_serving_full_text="2 tbsp",
        label_nutrients=LabelNutrients(),
        trade_channels=["NO_TRADE_CHANNEL"],
        microbes=[],
        food_update_log=[],
        data_type="Branded",
        fdc_id=2345678,
        publication_date="5/15/2026",
    )


def test_save_foundations_indexes_normalized_document(
    initialized_elasticsearch: str,
    foundation_food: FoundationFood,
) -> None:
    async def scenario() -> dict:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            await USDARepository(client).save_foundations([foundation_food])

        return await get_document(
            initialized_elasticsearch,
            index="usda-foundation-foods",
            document_id="usda-fdc:321358",
        )

    stored = run(scenario())

    assert stored["_index"] == "usda-foundation-foods-v1"
    assert stored["_source"] == {
        "id": "usda-fdc:321358",
        "source": "usda_fdc",
        "entity_type": "foundation_food",
        "label": "Hummus, prepared from chickpeas",
        "description": None,
        "fdc_id": 321358,
        "category": "Legumes and Legume Products",
        "scientific_name": "Cicer arietinum",
        "publication_date": "4/1/2019",
        "nutrients": [
            {
                "id": 1008,
                "number": "208",
                "name": "Energy",
                "unit": "kcal",
                "amount": 166.0,
            }
        ],
    }


def test_save_branded_indexes_normalized_document(
    initialized_elasticsearch: str,
    branded_food: BrandedFood,
) -> None:
    async def scenario() -> dict:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            await USDARepository(client).save_branded([branded_food])

        return await get_document(
            initialized_elasticsearch,
            index="usda-branded-foods",
            document_id="usda-fdc:2345678",
        )

    stored = run(scenario())

    assert stored["_index"] == "usda-branded-foods-v1"
    assert stored["_source"] == {
        "id": "usda-fdc:2345678",
        "source": "usda_fdc",
        "entity_type": "branded_food",
        "label": "Classic Hummus",
        "description": "Chickpea dip",
        "fdc_id": 2345678,
        "category": "Dips and spreads",
        "brand_owner": "Example Foods Inc.",
        "brand_name": "Example",
        "gtin_upc": "012345678901",
        "ingredients": "CHICKPEAS, TAHINI, OLIVE OIL",
        "market_country": "United States",
        "publication_date": "5/15/2026",
        "serving_size": 28.0,
        "serving_size_unit": "g",
        "nutrients": [
            {
                "id": 1008,
                "number": "208",
                "name": "Energy",
                "unit": "kcal",
                "amount": 166.0,
            }
        ],
    }
