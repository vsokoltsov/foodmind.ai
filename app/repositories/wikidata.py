"""Elasticsearch persistence for normalized Wikidata food entities."""

from dataclasses import dataclass, field
from typing import Any, cast

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

from app.aggregates import FoodEntity
from app.repositories.queries import WikidataFoodQuery
from app.repositories.hybrid import HybridRetriever


@dataclass
class WikidataFoodRepository:
    """Store Wikidata food records in their stable Elasticsearch write alias."""

    client: AsyncElasticsearch
    index_name: str = "wikidata-food-entities"
    hybrid_retriever: HybridRetriever = field(default_factory=HybridRetriever)

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

    async def get_by_id(self, entity_id: str) -> FoodEntity | None:
        """Retrieve one food concept by its Wikidata identifier."""
        try:
            response = await self.client.get(
                index=self.index_name,
                id=f"wikidata:{entity_id.removeprefix('wikidata:')}",
            )
        except NotFoundError:
            return None
        if not response.get("found", True):
            return None
        source = dict(response["_source"])
        source["id"] = str(source["id"]).removeprefix("wikidata:")
        source.pop("source", None)
        source.pop("entity_type", None)
        return FoodEntity.model_validate(source)

    async def search(self, query: WikidataFoodQuery) -> list[FoodEntity]:
        """Search food concepts by text and related cuisine or country."""
        filters: list[dict[str, object]] = []
        if query.cuisine_id:
            filters.append({"term": {"cuisines.id": query.cuisine_id}})
        if query.country_id:
            filters.append({"term": {"countries.id": query.country_id}})
        body: dict[str, object] = {"bool": {"filter": filters}}
        if query.text:
            body["bool"]["must"] = [{"multi_match": {"query": query.text, "fields": ["label", "description", "aliases"]}}]  # type: ignore[index]
        retriever = self.hybrid_retriever.build(body, query)
        if retriever is not None:
            response = await self.client.search(index=self.index_name, retriever=retriever, from_=query.offset, size=query.limit)
        else:
            response = await self.client.search(index=self.index_name, query=body, from_=query.offset, size=query.limit)
        return [self._from_hit(hit) for hit in response["hits"]["hits"]]

    @staticmethod
    def _from_hit(hit: dict[str, object]) -> FoodEntity:
        """Convert an Elasticsearch hit into a domain entity."""
        source = cast(dict[str, Any], hit["_source"])
        source["id"] = str(source["id"]).removeprefix("wikidata:")
        source.pop("source", None)
        source.pop("entity_type", None)
        return FoodEntity.model_validate(source)
