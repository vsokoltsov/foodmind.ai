"""Feedback business object."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Feedback(BaseModel):
    """One user's usefulness assessment of an assistant message."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    user_id: UUID
    is_useful: bool
