"""Tests for Elasticsearch hybrid retriever construction."""

from app.repositories.hybrid import HybridRetriever
from app.repositories.queries import SearchQuery


def test_without_embedding_uses_existing_bm25_path() -> None:
    """No embedding keeps the ordinary lexical search behavior."""
    assert HybridRetriever().build({"bool": {"filter": []}}, SearchQuery()) is None


def test_embedding_builds_rrf_with_lexical_and_knn_retrievers() -> None:
    """An embedding produces an RRF retriever with both search branches."""
    query = SearchQuery(text="apple", embedding=[0.1, 0.2], limit=5)
    result = HybridRetriever().build(
        {"bool": {"filter": [{"term": {"source": "usda"}}]}}, query
    )

    assert result is not None
    retrievers = result["rrf"]["retrievers"]
    assert "standard" in retrievers[0]
    assert retrievers[1]["knn"]["field"] == "embedding"
    assert retrievers[1]["knn"]["query_vector"] == [0.1, 0.2]
