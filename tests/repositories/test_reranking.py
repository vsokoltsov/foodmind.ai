"""Tests for deterministic document reranking."""

from app.repositories.reranking import DocumentReranker


def test_reranker_prefers_exact_label_match() -> None:
    """An exact label phrase outranks a weaker lexical candidate."""
    reranker = DocumentReranker()
    hits = [
        {"_score": 3.0, "_source": {"label": "Fruit drink"}},
        {"_score": 2.0, "_source": {"label": "Apple juice"}},
    ]

    result = reranker.rerank(hits, "apple juice", 1)

    assert result[0]["_source"]["label"] == "Apple juice"


def test_reranker_returns_original_order_without_query() -> None:
    """Queries without text retain Elasticsearch ordering."""
    hits = [{"_score": 2.0}, {"_score": 1.0}]

    assert DocumentReranker().rerank(hits, None, 1) == hits[:1]
