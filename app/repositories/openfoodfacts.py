"""Elasticsearch persistence for Open Food Facts products."""

from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.aggregates import OpenFoodFactsProduct as OpenFoodFactsAggregate
from app.clients.openfoodfacts.models import OpenFoodFactsProduct as ClientProduct
from app.repositories.models import OpenFoodFactsDocument
from app.repositories.queries import OpenFoodFactsQuery


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

    async def get_by_id(self, product_id: str) -> OpenFoodFactsAggregate | None:
        """Retrieve one product by its barcode or canonical product ID."""
        document_id = product_id.removeprefix("openfoodfacts:")
        response = await self.client.get(index=self.index_name, id=f"openfoodfacts:{document_id}")
        if not response.get("found", True):
            return None
        return OpenFoodFactsAggregate.model_validate(response["_source"])

    async def search(self, query: OpenFoodFactsQuery) -> list[OpenFoodFactsAggregate]:
        """Search products by text, barcode, brand, or country."""
        filters: list[dict[str, object]] = []
        if query.barcode:
            filters.append({"term": {"code": query.barcode}})
        if query.brand:
            filters.append({"match": {"brands": query.brand}})
        if query.country:
            filters.append({"match": {"countries": query.country}})
        body: dict[str, object] = {"bool": {"filter": filters}}
        if query.text:
            body["bool"]["must"] = [{"multi_match": {"query": query.text, "fields": ["label", "description", "ingredients", "categories"]}}]  # type: ignore[index]
        response = await self.client.search(index=self.index_name, query=body, from_=query.offset, size=query.limit)
        return [OpenFoodFactsAggregate.model_validate(hit["_source"]) for hit in response["hits"]["hits"]]
