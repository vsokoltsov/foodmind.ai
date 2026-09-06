"""Application lifespan and process-scoped resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI

from app.evaluation.artifacts import EvaluationArtifactRepository
from app.messaging.broker import ChatCommandBroker
from app.observability.tracing import tracing
from app.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ApplicationState:
    """Resources shared by API requests for the process lifetime."""

    elasticsearch: AsyncElasticsearch
    chat_broker: ChatCommandBroker
    retrieval_approach: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and close shared external clients with the application."""
    client = AsyncElasticsearch(get_settings().ELASTICSEARCH_URL)
    chat_broker = ChatCommandBroker(get_settings().NATS_URL)
    retrieval_approach: str | None = None
    try:
        artifact = await EvaluationArtifactRepository().load("retrieval")
        retrieval_approach = artifact.best_approach
        logger.info("Loaded retrieval approach from evaluation: %s", retrieval_approach)
    except Exception as error:
        logger.warning("Retrieval evaluation artifact is unavailable: %s", error)
    app.state.resources = ApplicationState(
        elasticsearch=client,
        chat_broker=chat_broker,
        retrieval_approach=retrieval_approach,
    )
    await chat_broker.start()
    try:
        yield
    finally:
        await chat_broker.stop()
        await client.close()
        tracing.shutdown()
