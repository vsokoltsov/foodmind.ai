"""Pydantic contracts exchanged between the API and chat worker."""

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, JsonValue


class ChatEventName(StrEnum):
    """Execution events that can be sent from a worker to the API."""

    USER_MESSAGE_PERSISTED = "user_message_persisted"
    ORCHESTRATOR_COMPLETED = "orchestrator_completed"
    ASSISTANT_MESSAGE_PERSISTED = "assistant_message_persisted"
    PLANNER_ERROR = "planner_error"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    QUERY_REWRITTEN = "query_rewritten"
    COMPLETED = "completed"
    ERROR = "error"


class ChatCommand(BaseModel):
    """Durable command instructing a worker to process one chat turn."""

    execution_id: UUID = Field(default_factory=uuid4)
    chat_id: UUID
    user_id: UUID
    content: str = Field(min_length=1)


class ChatExecutionResult(BaseModel):
    """Persisted final result of a chat command."""

    chat_id: UUID
    message_id: UUID
    answer: str
    used_agents: list[str] = Field(default_factory=list)
    selected_agents: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    durations_ms: dict[str, float] = Field(default_factory=dict)


class ChatExecutionEvent(BaseModel):
    """An execution update correlated to one durable chat command."""

    execution_id: UUID
    event: ChatEventName
    data: dict[str, JsonValue] = Field(default_factory=dict)
