"""Application lifespan and process-scoped resources."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import AsyncIterator

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI

from app.agents.orchestrator import FoodMindOrchestrator
from app.settings import get_settings


@dataclass
class ApplicationState:
    """Resources shared by API requests for the process lifetime."""

    elasticsearch: AsyncElasticsearch
    orchestrator: FoodMindOrchestrator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and close shared external clients with the application."""
    client = AsyncElasticsearch(get_settings().ELASTICSEARCH_URL)
    app.state.resources = ApplicationState(
        elasticsearch=client,
        orchestrator=FoodMindOrchestrator(),
    )
    try:
        yield
    finally:
        await client.close()
