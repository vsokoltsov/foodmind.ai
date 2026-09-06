"""Tests for retrieval query rewriting."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agents.query_rewriter import (
    QueryRewriteMethod,
    QueryRewriter,
    RewrittenQuery,
)
from app.settings import ModelSettings
from tests.repositories.conftest import run


def test_query_rewriter_uses_deterministic_normalization_without_an_api_key(
    monkeypatch,
) -> None:
    """Conversational filler is removed when model rewriting is unavailable."""
    settings = SimpleNamespace(
        OPENAI_API_KEY=None,
        OPENAI_MODEL="openai:test-model",
        OPENAI_PLANNER_MODEL=None,
        OPENAI_QUERY_REWRITER_MODEL=None,
        QUERY_REWRITE_TIMEOUT_SECONDS=1.0,
        models=SimpleNamespace(
            query_rewriter=ModelSettings(provider="openai", model="test-model")
        ),
    )
    monkeypatch.setattr("app.agents.query_rewriter.get_settings", lambda: settings)

    async def scenario() -> None:
        rewrite = await QueryRewriter().rewrite("Could you find low sodium soup?")

        assert rewrite.query == "find low sodium soup?"
        assert rewrite.method is QueryRewriteMethod.DETERMINISTIC

    run(scenario())


def test_query_rewriter_uses_structured_model_output(monkeypatch) -> None:
    """The model's compact query becomes the query sent to retrieval."""
    settings = SimpleNamespace(
        OPENAI_API_KEY="test-key",
        OPENAI_MODEL="openai:test-model",
        OPENAI_PLANNER_MODEL=None,
        OPENAI_QUERY_REWRITER_MODEL="openai:rewrite-model",
        QUERY_REWRITE_TIMEOUT_SECONDS=1.0,
        models=SimpleNamespace(
            query_rewriter=ModelSettings(provider="openai", model="rewrite-model")
        ),
    )
    monkeypatch.setattr("app.agents.query_rewriter.get_settings", lambda: settings)

    async def scenario() -> None:
        rewriter = QueryRewriter()
        rewriter.agent.run = AsyncMock(
            return_value=SimpleNamespace(
                output=RewrittenQuery(
                    query="vegetarian high protein foods under 300 calories"
                ),
                usage=SimpleNamespace(input_tokens=5, output_tokens=4),
            )
        )

        rewrite = await rewriter.rewrite("Please recommend vegetarian protein foods")

        assert rewrite.query == "vegetarian high protein foods under 300 calories"
        assert rewrite.method is QueryRewriteMethod.LLM

    run(scenario())
