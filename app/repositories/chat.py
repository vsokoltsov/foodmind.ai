"""Async repositories for chat persistence models."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aggregates import Conversation as ConversationAggregate
from app.aggregates import Message as MessageAggregate
from app.aggregates import TurnExecution as TurnExecutionAggregate
from app.models.chat import (
    Conversation as ConversationModel,
    Message as MessageModel,
    TurnExecution as TurnExecutionModel,
)


class ConversationRepository:
    """Persist and retrieve conversations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def create(self, entity: ConversationAggregate) -> ConversationModel:
        """Create and flush a conversation."""
        conversation = ConversationModel(
            id=entity.id,
            user_id=entity.user_id,
            title=entity.title,
            summary=entity.summary,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, conversation_id: UUID) -> ConversationModel | None:
        """Return a conversation by identifier."""
        return await self.session.get(ConversationModel, conversation_id)

    async def list(self, *, user_id: UUID | None = None) -> Sequence[ConversationModel]:
        """Return conversations, optionally restricted to a user."""
        statement = select(ConversationModel).order_by(ConversationModel.updated_at.desc())
        if user_id is not None:
            statement = statement.where(ConversationModel.user_id == user_id)
        result = await self.session.scalars(statement)
        return result.all()

    async def update(self, conversation: ConversationModel, **values: Any) -> ConversationModel:
        """Update allowed conversation attributes and flush the change."""
        for name in ("user_id", "title", "summary"):
            if name in values:
                setattr(conversation, name, values[name])
        await self.session.flush()
        return conversation

    async def delete(self, conversation: ConversationModel) -> None:
        """Delete a conversation and flush the change."""
        await self.session.delete(conversation)
        await self.session.flush()


class MessageRepository:
    """Persist and retrieve conversation messages."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def create(self, entity: MessageAggregate) -> MessageModel:
        """Create and flush a message."""
        message = MessageModel(
            id=entity.id,
            conversation_id=entity.conversation_id,
            role=entity.role,
            content=entity.content,
            agent_name=entity.agent_name,
            message_metadata=entity.message_metadata,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def get(self, message_id: UUID) -> MessageModel | None:
        """Return a message by identifier."""
        return await self.session.get(MessageModel, message_id)

    async def list_by_conversation(self, conversation_id: UUID) -> Sequence[MessageModel]:
        """Return messages in chronological order for a conversation."""
        result = await self.session.scalars(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
        )
        return result.all()

    async def delete(self, message: MessageModel) -> None:
        """Delete a message and flush the change."""
        await self.session.delete(message)
        await self.session.flush()


class TurnExecutionRepository:
    """Persist orchestrator execution state for conversations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def create(self, entity: TurnExecutionAggregate) -> TurnExecutionModel:
        """Create and flush a turn execution."""
        execution = TurnExecutionModel(
            id=entity.id,
            conversation_id=entity.conversation_id,
            user_message_id=entity.user_message_id,
            status=entity.status,
            original_query=entity.original_query,
            rewritten_query=entity.rewritten_query,
            selected_agents=entity.selected_agents,
            retrieved_evidence=entity.retrieved_evidence,
            completed_steps=entity.completed_steps,
            errors=entity.errors,
            retry_counts=entity.retry_counts,
            clarification_question=entity.clarification_question,
            missing_fields=entity.missing_fields,
            completed_at=entity.completed_at,
        )
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def get(self, execution_id: UUID) -> TurnExecutionModel | None:
        """Return an execution by identifier."""
        return await self.session.get(TurnExecutionModel, execution_id)

    async def get_for_message(
        self, user_message_id: UUID
    ) -> TurnExecutionModel | None:
        """Return the execution associated with a user message."""
        result = await self.session.scalars(
            select(TurnExecutionModel).where(
                TurnExecutionModel.user_message_id == user_message_id
            )
        )
        return result.one_or_none()

    async def update(
        self, execution: TurnExecutionModel, **values: Any
    ) -> TurnExecutionModel:
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

    async def delete(self, execution: TurnExecutionModel) -> None:
        """Delete an execution and flush the change."""
        await self.session.delete(execution)
        await self.session.flush()
