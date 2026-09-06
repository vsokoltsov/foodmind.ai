"""FastStream broker used by the API to submit and observe chat commands."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

from faststream.nats import JStream, NatsBroker

from app.messaging.models import (
    ChatCommand,
    ChatExecutionEvent,
)


CHAT_COMMAND_SUBJECT: Final = "foodmind.chat.commands"
CHAT_EVENT_SUBJECT: Final = "foodmind.chat.events"
CHAT_COMMAND_STREAM: Final = JStream(
    name="foodmind_chat_commands",
    subjects=[CHAT_COMMAND_SUBJECT],
    max_age=86_400,
)


@dataclass
class ChatCommandBroker:
    """Publish chat commands and route worker events to waiting API requests."""

    url: str
    _broker: NatsBroker = field(init=False)
    _queues: dict[UUID, asyncio.Queue[ChatExecutionEvent]] = field(
        init=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        """Create the FastStream NATS broker and event subscriber."""
        self._broker = NatsBroker(self.url, name="foodmind-api")
        self._broker.subscriber(CHAT_EVENT_SUBJECT)(self._route_event)

    async def start(self) -> None:
        """Connect the API process and start receiving worker events."""
        await self._broker.start()

    async def stop(self) -> None:
        """Drain the NATS connection during API shutdown."""
        await self._broker.stop()

    async def publish(self, command: ChatCommand) -> None:
        """Publish a command without waiting for worker execution."""
        await self._broker.publish(command, CHAT_COMMAND_SUBJECT)

    @asynccontextmanager
    async def submit(
        self, command: ChatCommand
    ) -> AsyncIterator[asyncio.Queue[ChatExecutionEvent]]:
        """Publish a command and yield its in-process event queue."""
        queue: asyncio.Queue[ChatExecutionEvent] = asyncio.Queue()
        self._queues[command.execution_id] = queue
        try:
            await self.publish(command)
            yield queue
        finally:
            self._queues.pop(command.execution_id, None)

    async def _route_event(self, event: ChatExecutionEvent) -> None:
        """Deliver an event only to the HTTP request that owns its command."""
        queue = self._queues.get(event.execution_id)
        if queue is not None:
            await queue.put(event)
