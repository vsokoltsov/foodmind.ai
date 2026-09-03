"""Elasticsearch persistence for USDA FoodData Central food records."""

from dataclasses import dataclass, field

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

from app.aggregates import (
    BrandedFood as BrandedFoodAggregate,
    FoundationFood as FoundationFoodAggregate,
)
from app.clients.usda_fdc.models import (
    BrandedFood as ClientBrandedFood,
    FoundationFood as ClientFoundationFood,
)
from app.repositories.models import BrandedDocument, FoundationDocument
from app.repositories.hybrid import HybridRetriever
from app.repositories.reranking import DocumentReranker
from app.repositories.queries import BrandedFoodQuery, USDAFoodQuery


@dataclass
class USDARepository:
    """Store USDA records in the appropriate stable Elasticsearch aliases."""

    client: AsyncElasticsearch
    foundation_index_name: str = "usda-foundation-foods"
    branded_index_name: str = "usda-branded-foods"
    hybrid_retriever: HybridRetriever = field(default_factory=HybridRetriever)
    reranker: DocumentReranker = field(default_factory=DocumentReranker)

    async def save_foundations(self, foods: list[FoundationFoodAggregate]) -> None:
        """Insert or replace a batch of canonical Foundation Foods."""
        documents = [
            FoundationDocument.from_domain(
                food.to_domain() if isinstance(food, ClientFoundationFood) else food
            )
            for food in foods
        ]
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": self.foundation_index_name,
                    "_id": document.id,
                    "_source": document.model_dump(mode="json"),
                }
                for document in documents
            ),
            raise_on_error=True,
        )

    async def save_branded(self, foods: list[BrandedFoodAggregate]) -> None:
        """Insert or replace a batch of canonical Branded Foods."""
        documents = [
            BrandedDocument.from_domain(
                food.to_domain() if isinstance(food, ClientBrandedFood) else food
            )
            for food in foods
        ]
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": self.branded_index_name,
                    "_id": document.id,
                    "_source": document.model_dump(mode="json"),
                }
                for document in documents
            ),
            raise_on_error=True,
        )

    async def get_foundation_by_id(self, fdc_id: int | str) -> FoundationFoodAggregate | None:
        """Retrieve one USDA Foundation Food by FDC identifier."""
        return await self._get(self.foundation_index_name, fdc_id, FoundationFoodAggregate)

    async def get_branded_by_id(self, fdc_id: int | str) -> BrandedFoodAggregate | None:
        """Retrieve one USDA Branded Food by FDC identifier."""
        return await self._get(self.branded_index_name, fdc_id, BrandedFoodAggregate)

    async def search_foundations(self, query: USDAFoodQuery) -> list[FoundationFoodAggregate]:
        """Search USDA Foundation Foods by text and category."""
        return await self._search(self.foundation_index_name, query, FoundationFoodAggregate)

    async def search_branded(self, query: BrandedFoodQuery) -> list[BrandedFoodAggregate]:
        """Search USDA Branded Foods by text, category, and brand."""
        return await self._search(self.branded_index_name, query, BrandedFoodAggregate)

    async def _get(self, index: str, fdc_id: int | str, model: type[FoundationFoodAggregate] | type[BrandedFoodAggregate]):
        try:
            response = await self.client.get(index=index, id=f"usda-fdc:{fdc_id}")
        except NotFoundError:
            return None
        if not response.get("found", True):
            return None
        return model.model_validate(response["_source"])

    async def _search(self, index: str, query: USDAFoodQuery, model: type[FoundationFoodAggregate] | type[BrandedFoodAggregate]):
        filters: list[dict[str, object]] = []
        if query.category:
            filters.append({"match": {"category": query.category}})
        if isinstance(query, BrandedFoodQuery) and query.barcode:
            filters.append({"term": {"gtin_upc": query.barcode}})
        body: dict[str, object] = {"bool": {"filter": filters}}
        if query.text:
            body["bool"]["must"] = [{"multi_match": {"query": query.text, "fields": ["label", "description", "category"]}}]  # type: ignore[index]
        retriever = self.hybrid_retriever.build(body, query)
        if retriever is not None:
            response = await self.client.search(index=index, retriever=retriever, from_=query.offset, size=self.reranker.candidate_size(query.limit))
        else:
            response = await self.client.search(index=index, query=body, from_=query.offset, size=self.reranker.candidate_size(query.limit))
        hits = response["hits"]["hits"]
        if query.rerank:
            hits = self.reranker.rerank(hits, query.text, query.limit)
        else:
            hits = hits[: query.limit]
        return [model.model_validate(hit["_source"]) for hit in hits]
