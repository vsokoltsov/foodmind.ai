"""Async repository for user feedback on assistant messages."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aggregates.feedback import Feedback as FeedbackAggregate
from app.models.feedback import Feedback as FeedbackModel


class FeedbackRepository:
    """Persist and retrieve user feedback for assistant messages."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async database session."""
        self.session = session

    async def get_for_message(
        self, *, message_id: UUID, user_id: UUID
    ) -> FeedbackModel | None:
        """Return one user's feedback for a message, if it exists."""
        result = await self.session.scalars(
            select(FeedbackModel).where(
                FeedbackModel.message_id == message_id,
                FeedbackModel.user_id == user_id,
            )
        )
        return result.one_or_none()

    async def list_for_messages(
        self, *, message_ids: Sequence[UUID], user_id: UUID
    ) -> Sequence[FeedbackModel]:
        """Return a user's feedback for the supplied message identifiers."""
        if not message_ids:
            return []
        result = await self.session.scalars(
            select(FeedbackModel).where(
                FeedbackModel.message_id.in_(message_ids),
                FeedbackModel.user_id == user_id,
            )
        )
        return result.all()

    async def upsert(self, entity: FeedbackAggregate) -> FeedbackModel:
        """Create feedback or replace the existing value from the same user."""
        feedback = await self.get_for_message(
            message_id=entity.message_id, user_id=entity.user_id
        )
        if feedback is None:
            feedback = FeedbackModel(
                id=entity.id,
                message_id=entity.message_id,
                user_id=entity.user_id,
                is_useful=entity.is_useful,
            )
            self.session.add(feedback)
        else:
            feedback.is_useful = entity.is_useful
        await self.session.flush()
        return feedback

    async def delete(self, feedback: FeedbackModel) -> None:
        """Delete feedback and flush the change."""
        await self.session.delete(feedback)
        await self.session.flush()
