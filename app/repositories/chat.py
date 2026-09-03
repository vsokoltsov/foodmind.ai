"""Async repositories for chat persistence models."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation, Message, TurnExecution


class ConversationRepository:
    """Persist and retrieve conversations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def create(
        self, *, user_id: UUID | None = None, title: str | None = None
    ) -> Conversation:
        """Create and flush a conversation."""
        conversation = Conversation(user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation | None:
        """Return a conversation by identifier."""
        return await self.session.get(Conversation, conversation_id)

    async def list(self, *, user_id: UUID | None = None) -> Sequence[Conversation]:
        """Return conversations, optionally restricted to a user."""
        statement = select(Conversation).order_by(Conversation.updated_at.desc())
        if user_id is not None:
            statement = statement.where(Conversation.user_id == user_id)
        result = await self.session.scalars(statement)
        return result.all()

    async def update(self, conversation: Conversation, **values: Any) -> Conversation:
        """Update allowed conversation attributes and flush the change."""
        for name in ("user_id", "title", "summary"):
            if name in values:
                setattr(conversation, name, values[name])
        await self.session.flush()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        """Delete a conversation and flush the change."""
        await self.session.delete(conversation)
        await self.session.flush()


class MessageRepository:
    """Persist and retrieve conversation messages."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def create(
        self,
        *,
        conversation_id: UUID,
        role: str,
        content: str,
        agent_name: str | None = None,
        message_metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Create and flush a message."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            agent_name=agent_name,
            message_metadata=message_metadata or {},
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def get(self, message_id: UUID) -> Message | None:
        """Return a message by identifier."""
        return await self.session.get(Message, message_id)

    async def list_by_conversation(self, conversation_id: UUID) -> Sequence[Message]:
        """Return messages in chronological order for a conversation."""
        result = await self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return result.all()

    async def delete(self, message: Message) -> None:
        """Delete a message and flush the change."""
        await self.session.delete(message)
        await self.session.flush()


class TurnExecutionRepository:
    """Persist orchestrator execution state for conversations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def create(self, **values: Any) -> TurnExecution:
        """Create and flush a turn execution."""
        execution = TurnExecution(**values)
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def get(self, execution_id: UUID) -> TurnExecution | None:
        """Return an execution by identifier."""
        return await self.session.get(TurnExecution, execution_id)

    async def get_for_message(self, user_message_id: UUID) -> TurnExecution | None:
        """Return the execution associated with a user message."""
        result = await self.session.scalars(
            select(TurnExecution).where(
                TurnExecution.user_message_id == user_message_id
            )
        )
        return result.one_or_none()

    async def update(self, execution: TurnExecution, **values: Any) -> TurnExecution:
        """Update execution state fields and flush the change."""
        for name in (
            "status",
            "rewritten_query",
            "selected_agents",
            "retrieved_evidence",
            "completed_steps",
            "errors",
            "retry_counts",
            "clarification_question",
            "missing_fields",
            "completed_at",
        ):
            if name in values:
                setattr(execution, name, values[name])
        await self.session.flush()
        return execution

    async def delete(self, execution: TurnExecution) -> None:
        """Delete an execution and flush the change."""
        await self.session.delete(execution)
        await self.session.flush()
