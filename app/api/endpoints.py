"""HTTP endpoints for conversational FoodMind requests."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.aggregates import Conversation, Feedback
from app.database import SessionFactory
from app.messaging.models import (
    ChatCommand,
    ChatEventName,
    ChatExecutionResult,
)
from app.observability import metrics
from app.observability.tracing import tracing
from app.repositories.chat import (
    ConversationRepository,
    MessageRepository,
)
from app.repositories.feedback import FeedbackRepository

from app.api.lifespan import ApplicationState
from app.api.models import (
    ChatCreateRequest,
    ChatSubmissionResponse,
    FeedbackRequest,
    FeedbackResponse,
    ChatMessagesResponse,
    ChatRequest,
    ChatStreamRequest,
    ChatResponse,
    MessageResponse,
)

router = APIRouter()


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


@router.post("/chats", response_model=ChatSubmissionResponse, status_code=202)
async def create_chat(
    payload: ChatCreateRequest, request: Request
) -> ChatSubmissionResponse:
    """Create a chat and submit its initial message to the worker."""
    resources = _resources(request)
    async with SessionFactory() as session:
        conversation = await ConversationRepository(session).create(
            Conversation(
                user_id=payload.user_id,
                title=_chat_title(payload.message, payload.title),
            )
        )
        await session.commit()
    command = ChatCommand(
        chat_id=conversation.id,
        user_id=payload.user_id,
        content=payload.message,
    )
    await resources.chat_broker.publish(command)
    return ChatSubmissionResponse(
        chat_id=conversation.id, execution_id=command.execution_id
    )


@router.post("/chats/stream")
async def stream_chat(
    payload: ChatStreamRequest, request: Request
) -> StreamingResponse:
    """Stream chat execution lifecycle events and the final answer."""
    resources = _resources(request)

    async def events():
        try:
            yield _sse("started", {"message": "Request accepted"})
            chat_id: UUID | None = payload.chat_id
            if chat_id is None:
                async with SessionFactory() as session:
                    conversation = await ConversationRepository(session).create(
                        Conversation(
                            user_id=payload.user_id,
                            title=_chat_title(payload.message, payload.title),
                        )
                    )
                    chat_id = conversation.id
                    await session.commit()
                yield _sse("chat_created", {"chat_id": chat_id})
            else:
                async with SessionFactory() as session:
                    conversation = await ConversationRepository(session).get(chat_id)
                    if conversation is None or conversation.user_id != payload.user_id:
                        yield _sse("error", {"message": "Chat not found"})
                        return

            command = ChatCommand(
                chat_id=chat_id,
                user_id=payload.user_id,
                content=payload.message,
            )
            yield _sse("orchestrator_started", {})
            async with resources.chat_broker.submit(command) as queue:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=10)
                    except asyncio.TimeoutError:
                        yield _sse("progress", {"message": "Agents are still working"})
                        continue
                    match event.event:
                        case ChatEventName.COMPLETED:
                            result = ChatExecutionResult.model_validate(
                                event.data["result"]
                            )
                            yield _sse("completed", result.model_dump(mode="json"))
                            return
                        case ChatEventName.ERROR:
                            yield _sse("error", event.data)
                            return
                        case _:
                            yield _sse(event.event.value, event.data)
        except Exception as error:
            yield _sse("error", {"message": str(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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

        with tracing.span("foodmind.feedback.upsert") as span:
            feedback = await FeedbackRepository(session).upsert(
                Feedback(
                    message_id=message_id,
                    user_id=payload.user_id,
                    is_useful=payload.is_useful,
                )
            )
            await session.commit()
            span.set_attribute("foodmind.outcome", "success")
        metrics.record_feedback(is_useful=payload.is_useful)
        return FeedbackResponse(
            id=feedback.id,
            message_id=feedback.message_id,
            user_id=feedback.user_id,
            is_useful=feedback.is_useful,
        )


@router.post(
    "/chats/{chat_id}/messages",
    response_model=ChatSubmissionResponse,
    status_code=202,
)
async def chat(
    payload: ChatRequest, chat_id: UUID, request: Request
) -> ChatSubmissionResponse:
    """Publish a chat command and immediately acknowledge its acceptance."""
    resources = _resources(request)
    async with SessionFactory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get(chat_id)
        if conversation is None or conversation.user_id != payload.user_id:
            raise HTTPException(status_code=404, detail="Chat not found")

    command = ChatCommand(
        chat_id=conversation.id,
        user_id=payload.user_id,
        content=payload.message,
    )
    await resources.chat_broker.publish(command)
    return ChatSubmissionResponse(
        chat_id=conversation.id, execution_id=command.execution_id
    )
