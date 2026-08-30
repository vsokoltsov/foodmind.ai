"""Elasticsearch persistence for normalized Wikidata food entities."""

from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.aggregates import FoodEntity


@dataclass
class WikidataFoodRepository:
    """Store Wikidata food records in their stable Elasticsearch write alias."""

    client: AsyncElasticsearch
    index_name: str = "wikidata-food-entities"

    async def save_records(self, documents: list[FoodEntity]) -> None:
        """Insert or replace a batch of normalized Wikidata food records."""
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": self.index_name,
                    "_id": f"wikidata:{document.id}",
                    "_source": {
                        "id": f"wikidata:{document.id}",
                        "source": "wikidata",
                        "entity_type": "food_concept",
                        **document.model_dump(mode="json", exclude={"id"}),
                    },
                }
                for document in documents
            ),
            raise_on_error=True,
        )
