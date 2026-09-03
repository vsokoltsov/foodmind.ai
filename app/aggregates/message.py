"""Chat message business object."""

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """A message belonging to a conversation."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    agent_name: str | None = None
    message_metadata: dict[str, Any] = Field(default_factory=dict)
