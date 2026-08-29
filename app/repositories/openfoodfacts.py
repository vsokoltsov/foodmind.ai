"""Elasticsearch persistence for Open Food Facts products."""

from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.aggregates import OpenFoodFactsProduct as OpenFoodFactsAggregate
from app.clients.openfoodfacts.models import OpenFoodFactsProduct as ClientProduct
from app.repositories.models import OpenFoodFactsDocument


@dataclass
class OpenFoodFactsRepository:
    """Store Open Food Facts products in their stable write alias."""

    client: AsyncElasticsearch
    index_name: str = "openfoodfacts-products"

    async def save_records(self, products: list[OpenFoodFactsAggregate]) -> None:
        """Insert or replace a batch of canonical Open Food Facts products."""
        documents = [
            OpenFoodFactsDocument.from_domain(
                product.to_domain() if isinstance(product, ClientProduct) else product
            )
            for product in products
        ]
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
