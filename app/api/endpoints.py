"""HTTP endpoints for conversational FoodMind requests."""

from fastapi import APIRouter, HTTPException, Request, status

from app.agents.food_search import FoodSearchDependencies
from app.agents.orchestrator import OrchestratorDependencies
from app.aggregates import Conversation, Message
from app.database import SessionFactory
from app.repositories.chat import ConversationRepository, MessageRepository

from app.api.lifespan import ApplicationState
from app.api.models import ChatRequest, ChatResponse

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


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Store a user message, run the orchestrator, and store its answer."""
    resources = _resources(request)
    async with SessionFactory() as session:
        conversations = ConversationRepository(session)
        if payload.conversation_id is None:
            conversation = await conversations.create(Conversation())
        else:
            conversation = await conversations.get(payload.conversation_id)
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")

        messages = MessageRepository(session)
        await messages.create(Message(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
        ))
        dependencies = OrchestratorDependencies.from_repositories(
            FoodSearchDependencies.from_client(
                resources.elasticsearch, resources.retrieval_approach
            )
        )
        try:
            result = await resources.orchestrator.run(
                payload.message,
                deps=dependencies,
            )
        except Exception as error:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to process the request",
            ) from error

        assistant_message = await messages.create(Message(
            conversation_id=conversation.id,
            role="assistant",
            content=result.output.answer,
            agent_name=",".join(result.output.used_agents) or None,
        ))
        await session.commit()
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            answer=result.output.answer,
            used_agents=result.output.used_agents,
        )
