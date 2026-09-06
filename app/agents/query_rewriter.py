"""Query rewriting for retrieval-oriented FoodMind agent prompts."""

import asyncio
import re
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from app.aggregates.model_configuration import ModelRole
from app.agents.model_factory import ModelFactory
from app.observability import metrics
from app.observability.tracing import tracing
from app.settings import get_settings


class QueryRewriteMethod(StrEnum):
    """Identify the mechanism that produced a retrieval query."""

    LLM = "llm"
    DETERMINISTIC = "deterministic"


class RewrittenQuery(BaseModel):
    """Structured retrieval query produced by the query-rewriting model."""

    query: str = Field(min_length=1, max_length=500)


class QueryRewrite(BaseModel):
    """Auditable result of preparing a user request for retrieval."""

    query: str = Field(min_length=1, max_length=500)
    method: QueryRewriteMethod


@dataclass
class QueryRewriter:
    """Rewrite conversational requests into compact retrieval instructions."""

    instructions: str | None = None
    agent: Agent[None, RewrittenQuery] = field(init=False)

    def __post_init__(self) -> None:
        """Create the structured-output rewriting agent."""
        settings = get_settings()
        factory = ModelFactory(settings)
        model = factory.build(ModelRole.QUERY_REWRITER)
        self.agent = Agent(
            model,
            output_type=RewrittenQuery,
            instructions=(
                "Rewrite the user request into one compact food-catalog retrieval "
                "query. Preserve food names, brands, barcodes, ingredients, cuisines, "
                "countries, dietary restrictions, allergens, nutrition targets, units, "
                "and comparison criteria. Remove greetings and conversational filler. "
                "Do not answer the request, add facts, or drop constraints. "
                f"{self.instructions or ''}"
            ).strip(),
            defer_model_check=factory.defer_model_check(),
        )

    async def rewrite(self, query: str) -> QueryRewrite:
        """Return a compact retrieval query with a deterministic safe fallback.

        Args:
            query: Original user request.

        Returns:
            A rewritten query and the mechanism that produced it.
        """
        normalized = self._normalize(query)
        settings = get_settings()
        factory = ModelFactory(settings)
        if not factory.provider_is_configured(ModelRole.QUERY_REWRITER):
            return QueryRewrite(
                query=normalized, method=QueryRewriteMethod.DETERMINISTIC
            )

        model = factory.name_for(ModelRole.QUERY_REWRITER)
        with tracing.span("foodmind.query_rewriter") as span:
            try:
                result = await asyncio.wait_for(
                    self.agent.run(normalized),
                    timeout=settings.QUERY_REWRITE_TIMEOUT_SECONDS,
                )
            except Exception:
                span.set_attribute("foodmind.outcome", "fallback")
                metrics.record_llm_failure(
                    component="query_rewriter", agent="query_rewriter", model=model
                )
                return QueryRewrite(
                    query=normalized, method=QueryRewriteMethod.DETERMINISTIC
                )
            span.set_attribute("foodmind.outcome", "success")
            span.set_attribute("foodmind.query_rewrite_method", QueryRewriteMethod.LLM)
            span.set_attribute("gen_ai.request.model", model.removeprefix("openai:"))
            span.set_attribute("gen_ai.usage.input_tokens", result.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", result.usage.output_tokens)
        metrics.record_llm_usage(
            component="query_rewriter",
            agent="query_rewriter",
            model=model,
            usage=result.usage,
        )
        return QueryRewrite(query=result.output.query, method=QueryRewriteMethod.LLM)

    @staticmethod
    def _normalize(query: str) -> str:
        """Normalize whitespace and remove common conversational prefixes."""
        normalized = " ".join(query.split())
        normalized = re.sub(
            r"^(?:please\s+|can you\s+|could you\s+|would you\s+|i(?:'d| would) like to\s+)",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = normalized or query.strip()
        if not normalized:
            raise ValueError("Query cannot be empty")
        return normalized[:500].rstrip()
