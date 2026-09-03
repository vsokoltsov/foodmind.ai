"""Pydantic schemas used by the HTTP API."""

from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for submitting one user message."""

    message: str = Field(min_length=1)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    """Response containing the assistant message and conversation identifier."""

    conversation_id: UUID
    message_id: UUID
    answer: str
    used_agents: list[str] = Field(default_factory=list)
