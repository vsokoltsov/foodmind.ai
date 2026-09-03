"""Conversation business object."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Conversation(BaseModel):
    """A user conversation exchanged with the application."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID | None = None
    title: str | None = None
    summary: str | None = None
