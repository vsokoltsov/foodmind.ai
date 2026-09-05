"""HTTP endpoints for conversational FoodMind requests."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies
from app.aggregates import Conversation, Feedback, Message
from app.database import SessionFactory
from app.repositories.chat import (
    ConversationRepository,
    MessageRepository,
)
from app.repositories.feedback import FeedbackRepository

from app.api.lifespan import ApplicationState
from app.api.models import (
    ChatAnswerResponse,
    ChatCreateRequest,
    FeedbackRequest,
    FeedbackResponse,
    ChatMessagesResponse,
    ChatRequest,
    ChatStreamRequest,
    ChatResponse,
    MessageResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _sse(event: str, data: object) -> str:
    """Encode one server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _resources(request: Request) -> ApplicationState:
    """Return process-scoped API resources from request state."""
    return request.app.state.resources


def _chat_title(message: str, title: str | None) -> str:
    """Return an explicit title or a concise title derived from the first prompt."""
    if title:
        return title
    return " ".join(message.split())[:80]


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Report API availability and Elasticsearch connectivity."""
    resources = _resources(request)
    if not await resources.elasticsearch.ping():
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    return {"status": "ok"}


@router.post("/chats", response_model=ChatAnswerResponse, status_code=201)
async def create_chat(
    payload: ChatCreateRequest, request: Request
) -> ChatAnswerResponse:
    """Create a chat and process its initial message atomically."""
    resources = _resources(request)
    async with SessionFactory() as session:
        conversation = await ConversationRepository(session).create(
            Conversation(
                user_id=payload.user_id,
                title=_chat_title(payload.message, payload.title),
            )
        )
        return await _process_message(
            session, conversation.id, payload.message, resources
        )


@router.post("/chats/stream")
async def stream_chat(
    payload: ChatStreamRequest, request: Request
) -> StreamingResponse:
    """Stream chat execution lifecycle events and the final answer."""
    resources = _resources(request)

    async def events():
        async with SessionFactory() as session:
            try:
                queue: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue()

                async def publish(event: str, data: dict[str, object]) -> None:
                    await queue.put((event, data))

                yield _sse("started", {"message": "Request accepted"})
                chat_id: UUID | None = payload.chat_id
                if chat_id is None:
                    conversation = await ConversationRepository(session).create(
                        Conversation(
                            user_id=payload.user_id,
                            title=_chat_title(payload.message, payload.title),
                        )
                    )
                    chat_id = conversation.id
                    yield _sse("chat_created", {"chat_id": chat_id})
                else:
                    conversation = await ConversationRepository(session).get(chat_id)
                    if conversation is None or conversation.user_id != payload.user_id:
                        yield _sse("error", {"message": "Chat not found"})
                        return
                yield _sse("orchestrator_started", {})
                task = asyncio.create_task(
                    _process_message(
                        session,
                        chat_id,
                        payload.message,
                        resources,
                        event_callback=publish,
                    )
                )
                while not task.done():
                    try:
                        event, data = await asyncio.wait_for(queue.get(), timeout=10)
                        yield _sse(event, data)
                    except asyncio.TimeoutError:
                        yield _sse("progress", {"message": "Agents are still working"})
                while not queue.empty():
                    event, data = queue.get_nowait()
                    yield _sse(event, data)
                result = task.result()
                yield _sse("completed", result.model_dump(mode="json"))
            except Exception as error:
                await session.rollback()
                yield _sse("error", {"message": str(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _process_message(
    session: AsyncSession,
    chat_id: UUID,
    content: str,
    resources: ApplicationState,
    event_callback: Callable[[str, dict[str, object]], Awaitable[None]] | None = None,
) -> ChatAnswerResponse:
    """Persist a user message, run the orchestrator, and persist its answer."""
    messages = MessageRepository(session)
    await messages.create(
        Message(conversation_id=chat_id, role="user", content=content)
    )
    # Do not hold a database transaction open while agents and LLMs run.
    await session.commit()
    if event_callback is not None:
        await event_callback("user_message_persisted", {"chat_id": chat_id})
    dependencies = OrchestratorDependencies.from_repositories(
        FoodSearchDependencies.from_client(
            resources.elasticsearch, resources.retrieval_approach
        )
    )
    dependencies.event_callback = event_callback
    try:
        result = await resources.orchestrator.run(content, deps=dependencies)
        if event_callback is not None:
            await event_callback("orchestrator_completed", {})
    except Exception as error:
        logger.exception("FoodMind orchestrator failed for chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to process the request",
        ) from error

    try:
        assistant_message = await messages.create(
            Message(
                conversation_id=chat_id,
                role="assistant",
                content=result.output.answer,
                agent_name=",".join(result.output.used_agents) or None,
            )
        )
        await session.commit()
        if event_callback is not None:
            await event_callback("assistant_message_persisted", {"chat_id": chat_id})
    except Exception:
        await session.rollback()
        raise
    return ChatAnswerResponse(
        chat_id=chat_id,
        message_id=assistant_message.id,
        answer=result.output.answer,
        used_agents=result.output.used_agents,
        selected_agents=(
            dependencies.execution_state.selected_agents
            if dependencies.execution_state
            else []
        ),
        completed_steps=(
            dependencies.execution_state.completed_steps
            if dependencies.execution_state
            else []
        ),
        errors=(
            dependencies.execution_state.errors if dependencies.execution_state else []
        ),
        durations_ms=(
            dependencies.execution_state.durations_ms
            if dependencies.execution_state
            else {}
        ),
    )


@router.get("/chats", response_model=list[ChatResponse])
async def list_chats(
    request: Request, user_id: UUID = Query(...)
) -> list[ChatResponse]:
    """Return available chats ordered by recent activity."""
    async with SessionFactory() as session:
        chats = await ConversationRepository(session).list(user_id=user_id)
        return [
            ChatResponse(
                id=chat.id,
                user_id=chat.user_id,
                title=chat.title,
                summary=chat.summary,
            )
            for chat in chats
        ]


@router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: UUID, request: Request, user_id: UUID = Query(...)
) -> ChatResponse:
    """Return one chat by identifier."""
    async with SessionFactory() as session:
        chat = await ConversationRepository(session).get(chat_id)
        if chat is None or chat.user_id != user_id:
            raise HTTPException(status_code=404, detail="Chat not found")
        return ChatResponse(
            id=chat.id, user_id=chat.user_id, title=chat.title, summary=chat.summary
        )


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: UUID, request: Request, user_id: UUID = Query(...)
) -> None:
    """Delete a chat and its messages."""
    async with SessionFactory() as session:
        repository = ConversationRepository(session)
        chat = await repository.get(chat_id)
        if chat is None or chat.user_id != user_id:
            raise HTTPException(status_code=404, detail="Chat not found")
        await repository.delete(chat)
        await session.commit()


@router.get("/chats/{chat_id}/messages", response_model=ChatMessagesResponse)
async def list_chat_messages(
    chat_id: UUID, request: Request, user_id: UUID = Query(...)
) -> ChatMessagesResponse:
    """Return messages in chronological order for a chat."""
    async with SessionFactory() as session:
        chat = await ConversationRepository(session).get(chat_id)
        if chat is None or chat.user_id != user_id:
            raise HTTPException(status_code=404, detail="Chat not found")
        messages = await MessageRepository(session).list_by_conversation(chat_id)
        feedback_by_message = {
            feedback.message_id: feedback
            for feedback in await FeedbackRepository(session).list_for_messages(
                message_ids=[message.id for message in messages], user_id=user_id
            )
        }
        return ChatMessagesResponse(
            chat_id=chat_id,
            messages=[
                MessageResponse(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    agent_name=message.agent_name,
                    feedback=(
                        FeedbackResponse(
                            id=feedback.id,
                            message_id=feedback.message_id,
                            user_id=feedback.user_id,
                            is_useful=feedback.is_useful,
                        )
                        if (feedback := feedback_by_message.get(message.id)) is not None
                        else None
                    ),
                )
                for message in messages
            ],
        )


@router.put(
    "/chats/{chat_id}/messages/{message_id}/feedback",
    response_model=FeedbackResponse,
)
async def upsert_message_feedback(
    chat_id: UUID,
    message_id: UUID,
    payload: FeedbackRequest,
    request: Request,
) -> FeedbackResponse:
    """Record or replace a user's usefulness feedback for an assistant message."""
    async with SessionFactory() as session:
        conversation = await ConversationRepository(session).get(chat_id)
        if conversation is None or conversation.user_id != payload.user_id:
            raise HTTPException(status_code=404, detail="Chat not found")

        message = await MessageRepository(session).get(message_id)
        if (
            message is None
            or message.conversation_id != chat_id
            or message.role != "assistant"
        ):
            raise HTTPException(status_code=404, detail="Assistant message not found")

        feedback = await FeedbackRepository(session).upsert(
            Feedback(
                message_id=message_id,
                user_id=payload.user_id,
                is_useful=payload.is_useful,
            )
        )
        await session.commit()
        return FeedbackResponse(
            id=feedback.id,
            message_id=feedback.message_id,
            user_id=feedback.user_id,
            is_useful=feedback.is_useful,
        )


@router.post("/chats/{chat_id}/messages", response_model=ChatAnswerResponse)
async def chat(
    payload: ChatRequest, chat_id: UUID, request: Request
) -> ChatAnswerResponse:
    """Store a user message, run the orchestrator, and store its answer."""
    resources = _resources(request)
    async with SessionFactory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get(chat_id)
        if conversation is None or conversation.user_id != payload.user_id:
            raise HTTPException(status_code=404, detail="Chat not found")

        return await _process_message(
            session, conversation.id, payload.message, resources
        )
