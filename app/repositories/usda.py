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
    foundation_index_name: str = "usda-foundation-foods"
    branded_index_name: str = "usda-branded-foods"

    async def save_foundations(self, documents: list[FoundationFood]) -> None:
        """Insert or replace a batch of USDA Foundation Foods."""
        await self.save_foundation_documents(
            [FoundationDocument.from_usda(document) for document in documents]
        )

    async def save_foundation_documents(
        self,
        documents: list[FoundationDocument],
    ) -> None:
        """Insert or replace already-normalized Foundation documents."""
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

    async def save_branded(self, documents: list[BrandedFood]) -> None:
        """Insert or replace a batch of USDA Branded Foods."""
        await self.save_branded_documents(
            [BrandedDocument.from_usda(document) for document in documents]
        )

    async def save_branded_documents(
        self,
        documents: list[BrandedDocument],
    ) -> None:
        """Insert or replace already-normalized Branded documents."""
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
