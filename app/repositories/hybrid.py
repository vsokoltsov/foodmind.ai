"""Shared Elasticsearch hybrid retrieval component."""

from dataclasses import dataclass
from typing import Any

from app.repositories.queries import SearchQuery


@dataclass(frozen=True)
class HybridRetriever:
    """Build Elasticsearch lexical-plus-vector RRF retrievers."""

    def build(
        self, lexical_query: dict[str, Any], query: SearchQuery
    ) -> dict[str, Any] | None:
        """Build an RRF retriever when an embedding is supplied.

        Returns ``None`` for ordinary BM25 retrieval, preserving the existing
        behavior while allowing callers to opt into semantic retrieval.
        """
        if query.embedding is None:
            return None
        return {
            "rrf": {
                "retrievers": [
                    {"standard": {"query": lexical_query}},
                    {
                        "knn": {
                            "field": "embedding",
                            "query_vector": query.embedding,
                            "k": query.limit,
                            "num_candidates": query.vector_candidates,
                            "filter": lexical_query.get("bool", {}).get("filter", []),
                        }
                    },
                ],
                "rank_constant": 60,
                "rank_window_size": max(query.limit, 50),
            }
        }
