import pytest
from elasticsearch import AsyncElasticsearch

from app.clients.openfoodfacts.models import OpenFoodFactsProduct
from app.repositories.models import OpenFoodFactsDocument
from app.repositories.openfoodfacts import OpenFoodFactsRepository
from tests.repositories.conftest import run

pytestmark = pytest.mark.integration


@pytest.fixture
def product() -> OpenFoodFactsProduct:
    """Provide a representative Open Food Facts product."""
    return OpenFoodFactsProduct(
        code="0000101209159",
        product_name="Hazelnut and dark chocolate spread",
        generic_name="Cocoa and hazelnut spread",
        brands="Bovetti",
        brands_tags=["xx:bovetti"],
        categories="Spreads, Hazelnut spreads",
        categories_tags=["en:spreads", "en:hazelnut-spreads"],
        countries="France",
        countries_tags=["en:france"],
        ingredients_text="Hazelnuts, cocoa, sugar",
        ingredients_tags=["en:hazelnut", "en:cocoa", "en:sugar"],
        allergens="Nuts",
        allergens_tags=["en:nuts"],
        traces="Milk",
        traces_tags=["en:milk"],
        labels_tags=["en:no-gluten", "en:no-palm-oil"],
        quantity="350 g",
        serving_size="15 g",
        nutrition_grades="e",
        nova_group=3,
        nutriments={
            "energy-kcal_100g": 617,
            "fat_100g": 48.0,
            "salt_100g": 0.01,
        },
        image_url="https://images.openfoodfacts.org/product.jpg",
        image_front_url="https://images.openfoodfacts.org/front.jpg",
        last_modified_t=1786042527,
    )


def test_document_normalizes_open_food_facts_product(
    product: OpenFoodFactsProduct,
) -> None:
    document = OpenFoodFactsDocument.from_open_food_facts(product)

    assert document.id == "openfoodfacts:0000101209159"
    assert document.source == "openfoodfacts"
    assert document.entity_type == "product"
    assert document.label == "Hazelnut and dark chocolate spread"
    assert document.ingredients == "Hazelnuts, cocoa, sugar"
    assert document.nutrition_grade == "e"
    assert document.nutriments["energy-kcal_100g"] == 617


def test_save_records_indexes_complete_document_through_write_alias(
    initialized_elasticsearch: str,
    product: OpenFoodFactsProduct,
) -> None:
    async def scenario() -> tuple[dict, dict]:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            await OpenFoodFactsRepository(client).save_records([product])
            await client.indices.refresh(index="openfoodfacts-products")
            stored = await client.get(
                index="openfoodfacts-products",
                id="openfoodfacts:0000101209159",
            )
            mapping = await client.indices.get_mapping(
                index="openfoodfacts-products-v1"
            )
            return dict(stored), dict(mapping)

    stored, mapping = run(scenario())

    assert stored["_index"] == "openfoodfacts-products-v1"
    assert stored["_source"] == OpenFoodFactsDocument.from_open_food_facts(
        product
    ).model_dump(mode="json")
    properties = mapping["openfoodfacts-products-v1"]["mappings"]["properties"]
    assert properties["nutriments"]["type"] == "flattened"
    assert properties["code"]["type"] == "keyword"


def test_save_records_replaces_product_with_same_code(
    initialized_elasticsearch: str,
    product: OpenFoodFactsProduct,
) -> None:
    updated_product = product.model_copy(
        update={"product_name": "Updated chocolate spread"}
    )

    async def scenario() -> tuple[dict, int]:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            repository = OpenFoodFactsRepository(client)
            await repository.save_records([product])
            await repository.save_records([updated_product])
            await client.indices.refresh(index="openfoodfacts-products")
            stored = await client.get(
                index="openfoodfacts-products",
                id="openfoodfacts:0000101209159",
            )
            count = await client.count(
                index="openfoodfacts-products",
                query={
                    "term": {
                        "id": "openfoodfacts:0000101209159",
                    }
                },
            )
            return dict(stored), count["count"]

    stored, count = run(scenario())

    assert stored["_source"]["label"] == "Updated chocolate spread"
    assert count == 1


def test_save_records_accepts_empty_batch(
    initialized_elasticsearch: str,
) -> None:
    async def scenario() -> None:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            await OpenFoodFactsRepository(client).save_records([])

    run(scenario())
