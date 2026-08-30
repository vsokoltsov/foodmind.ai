import pytest
from elasticsearch import AsyncElasticsearch

from app.aggregates import FoodEntity, RelatedEntity
from app.repositories.wikidata import WikidataFoodRepository
from tests.repositories.conftest import get_document, run

pytestmark = pytest.mark.integration


@pytest.fixture
def food_record() -> FoodEntity:
    """Provide a representative normalized Wikidata food entity."""
    return FoodEntity(
        id="Q178",
        label="pasta",
        description="Italian food made from flour and water",
        aliases=["Italian pasta"],
        countries=[RelatedEntity(id="Q38", label="Italy")],
        cuisines=[RelatedEntity(id="Q192786", label="Italian cuisine")],
        instance_of=[RelatedEntity(id="Q746549", label="dish")],
        subclasses=[],
        images=["https://commons.wikimedia.org/example.jpg"],
        articles=["https://en.wikipedia.org/wiki/Pasta"],
    )


def test_save_records_indexes_complete_document_through_write_alias(
    initialized_elasticsearch: str,
    food_record: FoodEntity,
) -> None:
    async def scenario() -> dict:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            repository = WikidataFoodRepository(client)
            await repository.save_records([food_record])

        return await get_document(
            initialized_elasticsearch,
            index="wikidata-food-entities",
            document_id="wikidata:Q178",
        )

    stored = run(scenario())

    assert stored["_index"] == "wikidata-food-entities-v1"
    assert stored["_source"] == {
        "id": "wikidata:Q178",
        "source": "wikidata",
        "entity_type": "food_concept",
        "label": "pasta",
        "description": "Italian food made from flour and water",
        "aliases": ["Italian pasta"],
        "countries": [{"id": "Q38", "label": "Italy"}],
        "cuisines": [{"id": "Q192786", "label": "Italian cuisine"}],
        "instance_of": [{"id": "Q746549", "label": "dish"}],
        "subclasses": [],
        "images": ["https://commons.wikimedia.org/example.jpg"],
        "articles": ["https://en.wikipedia.org/wiki/Pasta"],
    }


def test_save_records_replaces_document_with_same_id(
    initialized_elasticsearch: str,
    food_record: FoodEntity,
) -> None:
    async def scenario() -> tuple[dict, int]:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            repository = WikidataFoodRepository(client)
            await repository.save_records([food_record])
            await repository.save_records(
                [food_record.model_copy(update={"label": "fresh pasta"})]
            )
            await client.indices.refresh(index="wikidata-food-entities")
            stored = await client.get(
                index="wikidata-food-entities",
                id="wikidata:Q178",
            )
            count = await client.count(
                index="wikidata-food-entities",
                query={"term": {"id": "wikidata:Q178"}},
            )
            return dict(stored), count["count"]

    stored, count = run(scenario())

    assert stored["_source"]["label"] == "fresh pasta"
    assert count == 1
