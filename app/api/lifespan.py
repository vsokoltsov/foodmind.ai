"""Application lifespan and process-scoped resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
import structlog

from app.evaluation.artifacts import EvaluationArtifactRepository
from app.messaging.broker import ChatCommandBroker
from app.observability.structured_logging import configure_structlog
from app.observability.tracing import tracing
from app.settings import get_settings


@dataclass
class ApplicationState:
    """Resources shared by API requests for the process lifetime."""

    elasticsearch: AsyncElasticsearch
    chat_broker: ChatCommandBroker
    retrieval_approach: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and close shared external clients with the application."""
    configure_structlog()
    logger = structlog.get_logger(__name__)
    client = AsyncElasticsearch(get_settings().ELASTICSEARCH_URL)
    chat_broker = ChatCommandBroker(get_settings().NATS_URL)
    retrieval_approach: str | None = None
    try:
        artifact = await EvaluationArtifactRepository().load("retrieval")
        retrieval_approach = artifact.best_approach
        logger.info(
            "retrieval_evaluation_artifact_loaded",
            retrieval_approach=retrieval_approach,
        )
    except Exception as error:
        logger.warning(
            "retrieval_evaluation_artifact_unavailable",
            error=str(error),
        )
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
