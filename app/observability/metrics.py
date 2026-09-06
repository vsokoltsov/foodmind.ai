"""Prometheus metrics for FoodMind request processing."""

from typing import Protocol

from prometheus_client import Counter, Gauge, Histogram


class Usage(Protocol):
    """The token fields reported by a completed PydanticAI run."""

    input_tokens: int
    output_tokens: int


class Metrics:
    """Collect bounded, application-level Prometheus metrics.

    This class intentionally accepts only low-cardinality labels. In particular,
    prompts, chat IDs, user IDs, document IDs, and exception messages must never
    be used as metric labels.
    """

    def __init__(self) -> None:
        """Register FoodMind metric collectors in the default registry."""
        self.api_requests = Counter(
            "foodmind_api_requests",
            "Number of completed FoodMind API requests.",
            ["method", "path", "status"],
        )
        self.api_request_duration = Histogram(
            "foodmind_api_request_duration_seconds",
            "Duration of completed FoodMind API requests.",
            ["method", "path", "status"],
        )
        self.api_requests_in_progress = Gauge(
            "foodmind_api_requests_in_progress",
            "Number of FoodMind API requests currently being handled.",
            ["method"],
        )

        self.orchestrator_runs = Counter(
            "foodmind_orchestrator_runs",
            "Number of completed orchestrator runs.",
            ["route", "outcome"],
        )
        self.orchestrator_duration = Histogram(
            "foodmind_orchestrator_duration_seconds",
            "End-to-end orchestrator execution duration.",
            ["route", "outcome"],
        )
        self.orchestrator_stage_duration = Histogram(
            "foodmind_orchestrator_stage_duration_seconds",
            "Duration of an orchestrator stage.",
            ["stage", "outcome"],
        )
        self.agent_runs = Counter(
            "foodmind_agent_runs",
            "Number of specialist-agent executions.",
            ["agent", "outcome", "cached"],
        )
        self.agent_duration = Histogram(
            "foodmind_agent_duration_seconds",
            "Duration of a specialist-agent execution.",
            ["agent", "outcome", "cached"],
        )
        self.tool_calls = Counter(
            "foodmind_tool_calls",
            "Number of agent retrieval-tool calls.",
            ["agent", "tool", "outcome"],
        )
        self.retrieval_operations = Counter(
            "foodmind_retrieval_operations",
            "Number of repository retrieval operations.",
            ["operation", "outcome", "cache"],
        )
        self.retrieval_duration = Histogram(
            "foodmind_retrieval_duration_seconds",
            "Duration of repository retrieval operations.",
            ["operation", "outcome", "cache"],
        )

        self.llm_requests = Counter(
            "foodmind_llm_requests",
            "Number of completed LLM runs.",
            ["component", "agent", "model", "outcome"],
        )
        self.llm_tokens = Counter(
            "foodmind_llm_tokens",
            "Number of tokens used by LLM runs.",
            ["component", "agent", "model", "direction"],
        )

        self.message_step_duration = Histogram(
            "foodmind_message_processing_step_duration_seconds",
            "Duration of a chat-message processing step.",
            ["step", "outcome"],
        )
        self.feedback_submissions = Counter(
            "foodmind_feedback_submissions",
            "Number of feedback submissions, including replacements.",
            ["is_useful"],
        )

    def record_api_request(
        self, *, method: str, path: str, status: int, duration_seconds: float
    ) -> None:
        """Record one completed HTTP request."""
        labels = {"method": method, "path": path, "status": str(status)}
        self.api_requests.labels(**labels).inc()
        self.api_request_duration.labels(**labels).observe(duration_seconds)

    def record_orchestrator_run(
        self, *, route: str, outcome: str, duration_seconds: float
    ) -> None:
        """Record an end-to-end orchestrator run."""
        self.orchestrator_runs.labels(route=route, outcome=outcome).inc()
        self.orchestrator_duration.labels(route=route, outcome=outcome).observe(
            duration_seconds
        )

    def record_stage(
        self, *, stage: str, outcome: str, duration_seconds: float
    ) -> None:
        """Record a planner, executor, synthesis, or persistence stage."""
        self.orchestrator_stage_duration.labels(stage=stage, outcome=outcome).observe(
            duration_seconds
        )

    def record_agent_run(
        self,
        *,
        agent: str,
        outcome: str,
        cached: bool,
        duration_seconds: float = 0.0,
    ) -> None:
        """Record one specialist execution or executor-cache hit."""
        labels = {"agent": agent, "outcome": outcome, "cached": str(cached).lower()}
        self.agent_runs.labels(**labels).inc()
        self.agent_duration.labels(**labels).observe(duration_seconds)

    def record_tool_call(self, *, agent: str, tool: str, outcome: str) -> None:
        """Record completion or failure of an agent-facing retrieval tool."""
        self.tool_calls.labels(agent=agent, tool=tool, outcome=outcome).inc()

    def record_retrieval(
        self,
        *,
        operation: str,
        outcome: str,
        cache: str,
        duration_seconds: float,
    ) -> None:
        """Record a repository retrieval operation and its cache status."""
        labels = {"operation": operation, "outcome": outcome, "cache": cache}
        self.retrieval_operations.labels(**labels).inc()
        self.retrieval_duration.labels(**labels).observe(duration_seconds)

    def record_llm_usage(
        self,
        *,
        component: str,
        agent: str,
        model: str,
        usage: Usage,
    ) -> None:
        """Record request count plus input and output tokens for an LLM run."""
        labels = {
            "component": component,
            "agent": agent,
            "model": model.removeprefix("openai:"),
            "outcome": "success",
        }
        self.llm_requests.labels(**labels).inc()
        token_labels = {key: value for key, value in labels.items() if key != "outcome"}
        self.llm_tokens.labels(**token_labels, direction="input").inc(
            usage.input_tokens
        )
        self.llm_tokens.labels(**token_labels, direction="output").inc(
            usage.output_tokens
        )

    def record_llm_failure(self, *, component: str, agent: str, model: str) -> None:
        """Record an LLM run that failed before a usage report was available."""
        self.llm_requests.labels(
            component=component,
            agent=agent,
            model=model.removeprefix("openai:"),
            outcome="error",
        ).inc()

    def record_message_step(
        self, *, step: str, outcome: str, duration_seconds: float
    ) -> None:
        """Record one persistence or orchestration stage of a chat turn."""
        self.message_step_duration.labels(step=step, outcome=outcome).observe(
            duration_seconds
        )

    def record_feedback(self, *, is_useful: bool) -> None:
        """Record one user feedback submission."""
        self.feedback_submissions.labels(is_useful=str(is_useful).lower()).inc()


metrics = Metrics()
