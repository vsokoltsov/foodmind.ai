"""Orchestrator turn execution business object."""

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TurnExecution(BaseModel):
    """Execution state captured while answering one user message."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    user_message_id: UUID
    status: str = "running"
    original_query: str
    rewritten_query: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    retrieved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    clarification_question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    completed_at: Any | None = None
