"""FastStream worker that executes durable FoodMind chat commands."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from elasticsearch import AsyncElasticsearch
from faststream import FastStream
from faststream.nats import NatsBroker
from prometheus_client import start_http_server

from app.agents.orchestrator import FoodMindOrchestrator
from app.evaluation.artifacts import EvaluationArtifactRepository
from app.messaging.broker import (
    CHAT_COMMAND_STREAM,
    CHAT_COMMAND_SUBJECT,
    CHAT_EVENT_SUBJECT,
)
from app.messaging.models import ChatCommand, ChatEventName, ChatExecutionEvent
from app.observability.tracing import tracing
from app.services.chat_processor import ChatProcessor
from app.settings import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()
broker = NatsBroker(settings.NATS_URL, name="foodmind-chat-worker")
app = FastStream(broker)


@dataclass
class WorkerResources:
    """Lazily initialized resources shared by one worker process."""

    processor: ChatProcessor | None = None
    elasticsearch: AsyncElasticsearch | None = None

    async def get_processor(self) -> ChatProcessor:
        """Create Elasticsearch and orchestrator resources on first command."""
        if self.processor is not None:
            return self.processor
        self.elasticsearch = AsyncElasticsearch(settings.ELASTICSEARCH_URL)
        retrieval_approach: str | None = None
        try:
            artifact = await EvaluationArtifactRepository().load("retrieval")
            retrieval_approach = artifact.best_approach
        except Exception as error:
            logger.warning("Retrieval evaluation artifact is unavailable: %s", error)
        self.processor = ChatProcessor(
            elasticsearch=self.elasticsearch,
            orchestrator=FoodMindOrchestrator(),
            retrieval_approach=retrieval_approach,
        )
        return self.processor

    async def close(self) -> None:
        """Close the worker Elasticsearch client on shutdown."""
        if self.elasticsearch is not None:
            await self.elasticsearch.close()


resources = WorkerResources()
metrics_server: tuple[Any, Any] | None = None


def _json_data(data: dict[str, Any]) -> dict[str, Any]:
    """Convert event payloads to JSON-safe values before publishing them."""
    return json.loads(json.dumps(data, default=str))


async def _publish_event(
    command: ChatCommand, event: ChatEventName, data: dict[str, Any]
) -> None:
    """Publish one correlated worker event for the API SSE relay."""
    await broker.publish(
        ChatExecutionEvent(
            execution_id=command.execution_id,
            event=event,
            data=_json_data(data),
        ),
        CHAT_EVENT_SUBJECT,
    )


@broker.subscriber(
    CHAT_COMMAND_SUBJECT,
    stream=CHAT_COMMAND_STREAM,
    durable="foodmind-chat-worker",
    pull_sub=True,
)
async def process_chat_command(command: ChatCommand) -> None:
    """Process one durable command and publish execution events and its result."""
    try:
        processor = await resources.get_processor()

        async def publish_progress(event: str, data: dict[str, Any]) -> None:
            await _publish_event(command, ChatEventName(event), data)

        result = await processor.process(command, publish_progress)
    except Exception:
        logger.exception("Chat command %s failed", command.execution_id)
        await _publish_event(
            command,
            ChatEventName.ERROR,
            {"message": "Unable to process the request"},
        )
        return
    await _publish_event(
        command,
        ChatEventName.COMPLETED,
        {"result": result.model_dump(mode="json")},
    )


@app.on_shutdown
async def close_resources() -> None:
    """Close worker resources after FastStream stops subscribers."""
    global metrics_server
    await resources.close()
    if metrics_server is not None:
        metrics_server[0].shutdown()
        metrics_server = None
    tracing.shutdown()


@app.on_startup
async def configure_observability() -> None:
    """Expose worker metrics and configure background-worker tracing."""
    global metrics_server
    if metrics_server is None:
        metrics_server = start_http_server(9100)
    tracing.configure()
