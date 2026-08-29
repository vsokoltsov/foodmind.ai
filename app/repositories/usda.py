"""Elasticsearch persistence for USDA FoodData Central food records."""

from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
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


@dataclass
class USDARepository:
    """Store USDA records in the appropriate stable Elasticsearch aliases."""

    client: AsyncElasticsearch
    foundation_index_name: str = "usda-foundation-foods"
    branded_index_name: str = "usda-branded-foods"

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
