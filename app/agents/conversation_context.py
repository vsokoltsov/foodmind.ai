"""Application service for constructing bounded model conversation context."""

from dataclasses import dataclass
from typing import Protocol, Sequence

from app.aggregates.conversation_context import (
    ContextMessage,
    ConversationContext,
    MessageRole,
)


class PersistedMessage(Protocol):
    """Minimal persisted-message shape required by the context builder."""

    role: str
    content: str


@dataclass(frozen=True)
class ConversationContextBuilder:
    """Build bounded context from persisted chat state for the orchestrator."""

    max_messages: int = 8
    max_message_chars: int = 1_500
    max_summary_chars: int = 2_000

    def build(
        self,
        *,
        summary: str | None,
        messages: Sequence[PersistedMessage],
        current_message: str,
    ) -> ConversationContext:
        """Select recent user/assistant messages in chronological order."""
        supported = [
            message
            for message in messages
            if message.role in (MessageRole.USER.value, MessageRole.ASSISTANT.value)
        ]
        selected = [
            ContextMessage(
                role=MessageRole(message.role),
                content=message.content[: self.max_message_chars],
            )
            for message in supported[-self.max_messages :]
            if message.content.strip()
        ]
        return ConversationContext(
            summary=summary[: self.max_summary_chars] if summary else None,
            recent_messages=selected,
            current_message=current_message,
        )
