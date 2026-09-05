from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.models.chat import Conversation, Message, TurnExecution
from app.aggregates import Conversation as ConversationAggregate
from app.aggregates import Message as MessageAggregate
from app.aggregates import TurnExecution as TurnExecutionAggregate
from app.repositories.chat import (
    ConversationRepository,
    MessageRepository,
    TurnExecutionRepository,
)
from tests.repositories.conftest import run


def test_conversation_repository_crud() -> None:
    async def scenario() -> None:
        session = MagicMock()
        session.get = AsyncMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()
        conversation = Conversation(user_id=uuid4(), title="Lunch")
        session.get.return_value = conversation
        repository = ConversationRepository(session)

        created = await repository.create(
            ConversationAggregate(user_id=conversation.user_id, title="Lunch")
        )
        fetched = await repository.get(conversation.id)
        await repository.update(created, title="Dinner", ignored="value")
        await repository.delete(created)

        assert fetched is conversation
        assert created.title == "Dinner"
        session.add.assert_called_once_with(created)
        session.delete.assert_awaited_once_with(created)

    run(scenario())


def test_message_repository_create_and_list() -> None:
    async def scenario() -> None:
        session = MagicMock()
        session.get = AsyncMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()
        session.scalars = AsyncMock()
        message = Message(conversation_id=uuid4(), role="user", content="Hi")
        session.get.return_value = message
        session.scalars.return_value = SimpleNamespace(all=lambda: [message])
        repository = MessageRepository(session)

        created = await repository.create(
            MessageAggregate(
                conversation_id=message.conversation_id,
                role="user",
                content="Hi",
            )
        )
        fetched = await repository.get(message.id)
        listed = await repository.list_by_conversation(message.conversation_id)
        await repository.delete(created)

        assert created.content == "Hi"
        assert fetched is message
        assert listed == [message]
        session.delete.assert_awaited_once_with(created)

    run(scenario())


def test_turn_execution_repository_actions() -> None:
    async def scenario() -> None:
        session = MagicMock()
        session.get = AsyncMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()
        session.scalars = AsyncMock()
        execution = TurnExecution(
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            original_query="find apples",
        )
        session.get.return_value = execution
        session.scalars.return_value = SimpleNamespace(one_or_none=lambda: execution)
        repository = TurnExecutionRepository(session)

        created = await repository.create(
            TurnExecutionAggregate(
                conversation_id=execution.conversation_id,
                user_message_id=execution.user_message_id,
                original_query=execution.original_query,
            )
        )
        assert await repository.get(execution.id) is execution
        assert await repository.get_for_message(execution.user_message_id) is execution
        await repository.update(created, status="completed", errors=["none"])
        await repository.delete(created)

        assert created.status == "completed"
        session.delete.assert_awaited_once_with(created)

    run(scenario())
