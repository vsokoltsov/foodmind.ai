"""Bounded conversation context passed to the orchestrator."""

from enum import StrEnum

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Roles that are safe to include in conversational model context."""

    USER = "user"
    ASSISTANT = "assistant"


class ContextSection(StrEnum):
    """Stable labels used when rendering context for an LLM prompt."""

    SUMMARY = "conversation summary"
    RECENT_MESSAGES = "recent conversation"
    CURRENT_MESSAGE = "current request"


class ContextMessage(BaseModel):
    """One user or assistant message selected for model context."""

    role: MessageRole
    content: str = Field(min_length=1)


class ConversationContext(BaseModel):
    """Bounded conversational context for one orchestrator execution."""

    summary: str | None = None
    recent_messages: list[ContextMessage] = Field(default_factory=list)
    current_message: str = Field(min_length=1)

    def render(self) -> str:
        """Render context with explicit boundaries for the language model."""
        sections: list[str] = []
        if self.summary:
            sections.append(f"{ContextSection.SUMMARY.value.title()}:\n{self.summary}")
        if self.recent_messages:
            history = "\n".join(
                f"{message.role.value.title()}: {message.content}"
                for message in self.recent_messages
            )
            sections.append(f"{ContextSection.RECENT_MESSAGES.value.title()}:\n{history}")
        sections.append(
            f"{ContextSection.CURRENT_MESSAGE.value.title()}:\n{self.current_message}"
        )
        return "\n\n".join(sections)
