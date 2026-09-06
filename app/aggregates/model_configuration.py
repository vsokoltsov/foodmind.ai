"""Typed model roles and providers shared across application components."""

from enum import StrEnum


class ModelRole(StrEnum):
    """Logical model roles used by FoodMind components."""

    QUERY_REWRITER = "query_rewriter"
    PLANNER = "planner"
    AGENT = "agent"
    SYNTHESIS = "synthesis"
    EVALUATION_JUDGE = "evaluation_judge"
    EMBEDDINGS = "embeddings"


class ModelProvider(StrEnum):
    """Model providers supported by FoodMind."""

    OPENAI = "openai"
    VERTEX = "vertex"
    GEMINI = "gemini"
