from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.aggregates.feedback import Feedback as FeedbackAggregate
from app.models.feedback import Feedback
from app.repositories.feedback import FeedbackRepository
from tests.repositories.conftest import run


def test_feedback_repository_creates_and_replaces_feedback() -> None:
    async def scenario() -> None:
        session = MagicMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()
        session.scalars = AsyncMock()
        message_id = uuid4()
        user_id = uuid4()
        repository = FeedbackRepository(session)

        session.scalars.return_value = SimpleNamespace(one_or_none=lambda: None)
        created = await repository.upsert(
            FeedbackAggregate(
                message_id=message_id,
                user_id=user_id,
                is_useful=True,
            )
        )

        existing = Feedback(message_id=message_id, user_id=user_id, is_useful=True)
        session.scalars.return_value = SimpleNamespace(
            one_or_none=lambda: existing,
            all=lambda: [existing],
        )
        updated = await repository.upsert(
            FeedbackAggregate(
                message_id=message_id,
                user_id=user_id,
                is_useful=False,
            )
        )
        listed = await repository.list_for_messages(
            message_ids=[message_id], user_id=user_id
        )
        await repository.delete(updated)

        assert created.is_useful is True
        assert updated is existing
        assert updated.is_useful is False
        assert listed == [existing]
        session.add.assert_called_once_with(created)
        session.delete.assert_awaited_once_with(existing)

    run(scenario())
