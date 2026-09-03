"""Deterministic document reranking for repository search results."""

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentReranker:
    """Rerank Elasticsearch hits using relevance and lexical query overlap."""

    candidate_multiplier: int = 3
    exact_phrase_boost: float = 2.0
    term_overlap_boost: float = 0.25

    def candidate_size(self, limit: int) -> int:
        """Return how many candidates should be retrieved before reranking."""
        return max(limit, limit * self.candidate_multiplier)

    def rerank(
        self, hits: list[dict[str, Any]], query: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Return the highest-scoring candidates, preserving hit payloads."""
        if not query or not hits:
            return hits[:limit]
        normalized_query = " ".join(query.casefold().split())
        query_terms = set(re.findall(r"\w+", normalized_query))
        scored = [(self._score(hit, normalized_query, query_terms), hit) for hit in hits]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[:limit]]

    def _score(
        self, hit: dict[str, Any], query: str, query_terms: set[str]
    ) -> float:
        """Calculate a transparent reranking score for one hit."""
        score = float(hit.get("_score") or 0.0)
        source = hit.get("_source", {})
        label = str(source.get("label") or "").casefold()
        if query in label:
            score += self.exact_phrase_boost
        label_terms = set(re.findall(r"\w+", label))
        score += len(query_terms & label_terms) * self.term_overlap_boost
        return score
