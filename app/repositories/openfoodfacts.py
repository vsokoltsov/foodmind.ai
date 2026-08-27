"""Elasticsearch persistence for Open Food Facts products."""

from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.clients.openfoodfacts.models import OpenFoodFactsProduct
from app.repositories.models import OpenFoodFactsDocument


@dataclass
class OpenFoodFactsRepository:
    """Store Open Food Facts products in their stable write alias."""

    client: AsyncElasticsearch

    async def save_records(self, documents: list[OpenFoodFactsProduct]) -> None:
        """Insert or replace a batch of Open Food Facts products."""
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": "openfoodfacts-products",
                    "_id": document.id,
                    "_source": document.model_dump(mode="json"),
                }
                for document in map(
                    OpenFoodFactsDocument.from_open_food_facts,
                    documents,
                )
            ),
            raise_on_error=True,
        )
