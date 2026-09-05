from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.api import endpoints
from app.api.models import ChatRequest
from tests.repositories.conftest import run


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


def _request(resources: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(resources=resources)))


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
        session = AsyncMock()
        orchestrator = AsyncMock()
        orchestrator.run.return_value = SimpleNamespace(
            output=SimpleNamespace(answer="Here are the results", used_agents=["food_search"])
        )
        resources = SimpleNamespace(
            elasticsearch=AsyncMock(),
            orchestrator=orchestrator,
            retrieval_approach=None,
        )

        class FakeConversationRepository:
            def __init__(self, _session):
                self.conversation = SimpleNamespace(id=conversation_id)

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
        monkeypatch.setattr(endpoints, "SessionFactory", lambda: _SessionContext(session))

        response = await endpoints.chat(
            ChatRequest(message="Find apples"),
            conversation_id,
            _request(resources),
        )

        assert response.answer == "Here are the results"
        assert response.used_agents == ["food_search"]
        orchestrator.run.assert_awaited_once()
        session.commit.assert_awaited_once()

    run(scenario())
