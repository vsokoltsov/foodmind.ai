"""Pydantic schemas used by the HTTP API."""

from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for submitting one user message."""

    message: str = Field(min_length=1)
    user_id: UUID


class ChatCreateRequest(BaseModel):
    """Metadata and the initial message for creating a chat."""

    title: str | None = None
    message: str = Field(min_length=1)
    user_id: UUID


class ChatStreamRequest(BaseModel):
    """Request body for streamed chat execution."""

    message: str = Field(min_length=1)
    user_id: UUID
    chat_id: UUID | None = None
    title: str | None = None


class FeedbackRequest(BaseModel):
    """A user's usefulness assessment for one assistant message."""

    user_id: UUID
    is_useful: bool


class FeedbackResponse(BaseModel):
    """Serialized feedback associated with one message."""

    id: UUID
    message_id: UUID
    user_id: UUID
    is_useful: bool


class MessageResponse(BaseModel):
    """Serialized chat message."""

    id: UUID
    role: str
    content: str
    agent_name: str | None = None
    feedback: FeedbackResponse | None = None


class ChatResponse(BaseModel):
    """Serialized chat summary."""

    id: UUID
    user_id: UUID
    title: str | None = None
    summary: str | None = None


class ChatMessagesResponse(BaseModel):
    """Messages belonging to one chat."""

    chat_id: UUID
    messages: list[MessageResponse]


class ChatSubmissionResponse(BaseModel):
    """Acknowledgement that a chat command was durably submitted."""

    chat_id: UUID
    execution_id: UUID
    status: str = "accepted"
