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
    index_name: str = "openfoodfacts-products"

    async def save_records(self, documents: list[OpenFoodFactsProduct]) -> None:
        """Insert or replace a batch of Open Food Facts products."""
        await self.save_documents(
            [OpenFoodFactsDocument.from_open_food_facts(document) for document in documents]
        )

    async def save_documents(
        self,
        documents: list[OpenFoodFactsDocument],
    ) -> None:
        """Insert or replace already-normalized Open Food Facts documents."""
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": self.index_name,
                    "_id": document.id,
                    "_source": document.model_dump(mode="json"),
                }
                for document in documents
            ),
            raise_on_error=True,
        )
