"""HTTP endpoints for conversational FoodMind requests."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies
from app.aggregates import Conversation, Message
from app.database import SessionFactory
from app.repositories.chat import ConversationRepository, MessageRepository

from app.api.lifespan import ApplicationState
from app.api.models import (
    ChatAnswerResponse,
    ChatCreateRequest,
    ChatMessagesResponse,
    ChatRequest,
    ChatResponse,
    MessageResponse,
)

router = APIRouter()


def _resources(request: Request) -> ApplicationState:
    """Return process-scoped API resources from request state."""
    return request.app.state.resources


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
            Conversation(title=payload.title)
        )
        return await _process_message(
            session, conversation.id, payload.message, resources
        )


async def _process_message(
    session: AsyncSession,
    chat_id: UUID,
    content: str,
    resources: ApplicationState,
) -> ChatAnswerResponse:
    """Persist a user message, run the orchestrator, and persist its answer."""
    messages = MessageRepository(session)
    await messages.create(
        Message(conversation_id=chat_id, role="user", content=content)
    )
    dependencies = OrchestratorDependencies.from_repositories(
        FoodSearchDependencies.from_client(
            resources.elasticsearch, resources.retrieval_approach
        )
    )
    try:
        result = await resources.orchestrator.run(content, deps=dependencies)
    except Exception as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to process the request",
        ) from error

    assistant_message = await messages.create(
        Message(
            conversation_id=chat_id,
            role="assistant",
            content=result.output.answer,
            agent_name=",".join(result.output.used_agents) or None,
        )
    )
    await session.commit()
    return ChatAnswerResponse(
        chat_id=chat_id,
        message_id=assistant_message.id,
        answer=result.output.answer,
        used_agents=result.output.used_agents,
    )


@router.get("/chats", response_model=list[ChatResponse])
async def list_chats(request: Request) -> list[ChatResponse]:
    """Return available chats ordered by recent activity."""
    async with SessionFactory() as session:
        chats = await ConversationRepository(session).list()
        return [ChatResponse(id=chat.id, title=chat.title, summary=chat.summary) for chat in chats]


@router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: UUID, request: Request) -> ChatResponse:
    """Return one chat by identifier."""
    async with SessionFactory() as session:
        chat = await ConversationRepository(session).get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        return ChatResponse(id=chat.id, title=chat.title, summary=chat.summary)


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(chat_id: UUID, request: Request) -> None:
    """Delete a chat and its messages."""
    async with SessionFactory() as session:
        repository = ConversationRepository(session)
        chat = await repository.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        await repository.delete(chat)
        await session.commit()


@router.get("/chats/{chat_id}/messages", response_model=ChatMessagesResponse)
async def list_chat_messages(
    chat_id: UUID, request: Request
) -> ChatMessagesResponse:
    """Return messages in chronological order for a chat."""
    async with SessionFactory() as session:
        if await ConversationRepository(session).get(chat_id) is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        messages = await MessageRepository(session).list_by_conversation(chat_id)
        return ChatMessagesResponse(
            chat_id=chat_id,
            messages=[
                MessageResponse(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    agent_name=message.agent_name,
                )
                for message in messages
            ],
        )


@router.post("/chats/{chat_id}/messages", response_model=ChatAnswerResponse)
async def chat(payload: ChatRequest, chat_id: UUID, request: Request) -> ChatAnswerResponse:
    """Store a user message, run the orchestrator, and store its answer."""
    resources = _resources(request)
    async with SessionFactory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get(chat_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Chat not found")

        return await _process_message(session, conversation.id, payload.message, resources)
