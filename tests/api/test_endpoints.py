from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.api import endpoints
from app.api.models import ChatRequest, FeedbackRequest
from tests.repositories.conftest import run


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


def _request(resources: object) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(resources=resources))
    )


def test_health_endpoint_reports_elasticsearch() -> None:
    async def scenario() -> None:
        elasticsearch = AsyncMock()
        elasticsearch.ping.return_value = True
        response = await endpoints.health(
            _request(SimpleNamespace(elasticsearch=elasticsearch))
        )
        assert response == {"status": "ok"}
        elasticsearch.ping.assert_awaited_once()

    run(scenario())


def test_chat_endpoint_runs_orchestrator_and_persists_messages(monkeypatch) -> None:
    async def scenario() -> None:
        conversation_id = uuid4()
        user_id = uuid4()
        session = AsyncMock()
        orchestrator = AsyncMock()
        orchestrator.run.return_value = SimpleNamespace(
            output=SimpleNamespace(
                answer="Here are the results", used_agents=["food_search"]
            )
        )
        resources = SimpleNamespace(
            elasticsearch=AsyncMock(),
            orchestrator=orchestrator,
            retrieval_approach=None,
        )

        class FakeConversationRepository:
            def __init__(self, _session):
                self.conversation = SimpleNamespace(id=conversation_id, user_id=user_id)

            async def create(self, _entity):
                return self.conversation

            async def get(self, _conversation_id):
                return self.conversation

        class FakeMessageRepository:
            def __init__(self, _session):
                self.calls = []

            async def create(self, entity):
                self.calls.append(entity)
                return SimpleNamespace(id=uuid4())

        monkeypatch.setattr(
            endpoints,
            "ConversationRepository",
            FakeConversationRepository,
        )
        monkeypatch.setattr(endpoints, "MessageRepository", FakeMessageRepository)
        monkeypatch.setattr(
            endpoints, "SessionFactory", lambda: _SessionContext(session)
        )

        response = await endpoints.chat(
            ChatRequest(message="Find apples", user_id=user_id),
            conversation_id,
            _request(resources),
        )

        assert response.answer == "Here are the results"
        assert response.used_agents == ["food_search"]
        orchestrator.run.assert_awaited_once()
        assert session.commit.await_count == 2

    run(scenario())


def test_feedback_endpoint_upserts_assistant_message_feedback(monkeypatch) -> None:
    async def scenario() -> None:
        chat_id = uuid4()
        message_id = uuid4()
        feedback_id = uuid4()
        user_id = uuid4()
        session = AsyncMock()

        class FakeConversationRepository:
            def __init__(self, _session):
                pass

            async def get(self, _chat_id):
                return SimpleNamespace(id=chat_id, user_id=user_id)

        class FakeMessageRepository:
            def __init__(self, _session):
                pass

            async def get(self, _message_id):
                return SimpleNamespace(
                    id=message_id, conversation_id=chat_id, role="assistant"
                )

        class FakeFeedbackRepository:
            def __init__(self, _session):
                pass

            async def upsert(self, entity):
                return SimpleNamespace(
                    id=feedback_id, **entity.model_dump(exclude={"id"})
                )

        monkeypatch.setattr(
            endpoints, "ConversationRepository", FakeConversationRepository
        )
        monkeypatch.setattr(endpoints, "MessageRepository", FakeMessageRepository)
        monkeypatch.setattr(endpoints, "FeedbackRepository", FakeFeedbackRepository)
        monkeypatch.setattr(
            endpoints, "SessionFactory", lambda: _SessionContext(session)
        )

        response = await endpoints.upsert_message_feedback(
            chat_id,
            message_id,
            FeedbackRequest(user_id=user_id, is_useful=True),
            _request(SimpleNamespace()),
        )

        assert response.id == feedback_id
        assert response.message_id == message_id
        assert response.user_id == user_id
        assert response.is_useful is True
        session.commit.assert_awaited_once()

    run(scenario())
