"""Tests for bounded conversational context construction."""

from types import SimpleNamespace

from app.aggregates import ContextSection, MessageRole
from app.agents.conversation_context import ConversationContextBuilder


def test_context_builder_keeps_recent_supported_messages_only() -> None:
    """Context excludes tool messages and applies the recent-message bound."""
    messages = [
        SimpleNamespace(role="system", content="internal"),
        SimpleNamespace(role="user", content="older"),
        SimpleNamespace(role="assistant", content="answer"),
        SimpleNamespace(role="tool", content="raw retrieval"),
    ]

    context = ConversationContextBuilder(max_messages=3).build(
        summary="Vegetarian user",
        messages=messages,
        current_message="What about the second option?",
    )

    assert [message.role for message in context.recent_messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]


def test_context_render_has_explicit_sections() -> None:
    """Rendered context clearly separates history from the current request."""
    context = ConversationContextBuilder().build(
        summary="Avoid peanuts",
        messages=[SimpleNamespace(role="user", content="Find vegetarian foods")],
        current_message="Under 300 calories",
    )

    rendered = context.render()

    assert f"{ContextSection.SUMMARY.value.title()}:" in rendered
    assert f"{ContextSection.RECENT_MESSAGES.value.title()}:" in rendered
    assert f"{ContextSection.CURRENT_MESSAGE.value.title()}:" in rendered
    assert "Under 300 calories" in rendered
