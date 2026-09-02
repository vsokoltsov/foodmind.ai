"""State captured while an orchestrated FoodMind request is running."""

from pydantic import BaseModel, Field


class ExecutionState(BaseModel):
    """Structured audit trail and guardrail state for one user request."""

    original_query: str
    rewritten_query: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    retrieved_evidence: dict[str, list[dict[str, object]]] = Field(default_factory=dict)
    completed_steps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    attempted_steps: list[str] = Field(default_factory=list)

    def select_agent(self, agent: str) -> None:
        """Record an agent selected for execution once."""
        if agent not in self.selected_agents:
            self.selected_agents.append(agent)

    def start_step(self, step: str) -> None:
        """Mark a step as attempted and reject exact duplicate execution."""
        if step in self.attempted_steps:
            raise ValueError(f"Step already attempted: {step}")
        self.attempted_steps.append(step)

    def complete_step(self, step: str, evidence: object) -> None:
        """Record successful completion and its returned evidence."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        if isinstance(evidence, BaseModel):
            value = evidence.model_dump(mode="json")
        elif isinstance(evidence, list):
            value = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in evidence]
        else:
            value = [evidence]
        self.retrieved_evidence[step] = [item if isinstance(item, dict) else {"value": item} for item in value]

    def record_error(self, step: str, error: Exception) -> None:
        """Record a failure and increment the step retry counter."""
        self.errors.append(f"{step}: {error}")
        self.retry_counts[step] = self.retry_counts.get(step, 0) + 1
