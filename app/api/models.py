"""Pydantic schemas used by the HTTP API."""

from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for submitting one user message."""

    message: str = Field(min_length=1)


class ChatCreateRequest(BaseModel):
    """Metadata and the initial message for creating a chat."""

    title: str | None = None
    message: str = Field(min_length=1)


class MessageResponse(BaseModel):
    """Serialized chat message."""

    id: UUID
    role: str
    content: str
    agent_name: str | None = None


class ChatResponse(BaseModel):
    """Serialized chat summary."""

    id: UUID
    title: str | None = None
    summary: str | None = None


class ChatMessagesResponse(BaseModel):
    """Messages belonging to one chat."""

    chat_id: UUID
    messages: list[MessageResponse]


class ChatAnswerResponse(BaseModel):
    """Response containing the assistant answer."""

    chat_id: UUID
    message_id: UUID
    answer: str
    used_agents: list[str] = Field(default_factory=list)
