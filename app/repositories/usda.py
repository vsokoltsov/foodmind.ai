"""Elasticsearch persistence for USDA FoodData Central food records."""

from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.clients.usda_fdc.models import BrandedFood, FoundationFood
from app.repositories.models import BrandedDocument, FoundationDocument


@dataclass
class USDARepository:
    """Store USDA records in the appropriate stable Elasticsearch aliases."""

    client: AsyncElasticsearch

    async def save_foundations(self, documents: list[FoundationFood]) -> None:
        """Insert or replace a batch of USDA Foundation Foods."""
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": "usda-foundation-foods",
                    "_id": document.id,
                    "_source": document.model_dump(mode="json"),
                }
                for document in map(FoundationDocument.from_usda, documents)
            ),
            raise_on_error=True,
        )

    async def save_branded(self, documents: list[BrandedFood]) -> None:
        """Insert or replace a batch of USDA Branded Foods."""
        await async_bulk(
            self.client,
            actions=(
                {
                    "_index": "usda-branded-foods",
                    "_id": document.id,
                    "_source": document.model_dump(mode="json"),
                }
                for document in map(BrandedDocument.from_usda, documents)
            ),
            raise_on_error=True,
        )
