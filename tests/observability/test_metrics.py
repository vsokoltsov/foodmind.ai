"""Tests for the Prometheus metrics exposed by FoodMind."""

from prometheus_client import generate_latest

from app.observability import metrics


class _Usage:
    """Minimal PydanticAI-compatible usage fixture."""

    input_tokens = 17
    output_tokens = 9


def test_foodmind_metrics_are_registered_and_observable() -> None:
    """FoodMind execution, token, and feedback metrics are exported."""
    metrics.record_orchestrator_run(
        route="direct", outcome="success", duration_seconds=0.1
    )
    metrics.record_llm_usage(
        component="agent",
        agent="food_search",
        model="openai:test-model",
        usage=_Usage(),
    )
    metrics.record_feedback(is_useful=True)

    exported = generate_latest().decode()

    assert "foodmind_orchestrator_runs_total" in exported
    assert "foodmind_llm_tokens_total" in exported
    assert "foodmind_feedback_submissions_total" in exported
