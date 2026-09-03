"""Retrieval-quality evaluation for Elasticsearch search strategies."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from elasticsearch import AsyncElasticsearch
from pydantic import BaseModel, Field

from app.repositories.reranking import DocumentReranker


class RetrievalApproach(StrEnum):
    """Retrieval strategies compared by the benchmark."""

    BM25 = "bm25"
    FILTERED_BM25 = "filtered_bm25"
    HYBRID = "hybrid"
    HYBRID_RERANKED = "hybrid_reranked"


class RetrievalEvaluationItem(BaseModel):
    """One query and its manually labelled relevant document IDs."""

    index: str
    query: str
    relevant_ids: list[str] = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class RetrievalEvaluationResult(BaseModel):
    """Metrics for one retrieval strategy on one query."""

    approach: RetrievalApproach
    index: str
    query: str
    retrieved_ids: list[str]
    recall_at_k: float
    reciprocal_rank: float
    error: str | None = None


class RetrievalEvaluationReport(BaseModel):
    """Persistable retrieval benchmark report and selected strategy."""

    results: list[RetrievalEvaluationResult]
    summary: list[dict[str, str | float | int]]
    best_approach: RetrievalApproach

    def save(self, path: Path) -> None:
        """Write the report as formatted JSON for CI artifacts."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")


@dataclass
class RetrievalEvaluationRunner:
    """Run and compare Elasticsearch retrieval strategies."""

    client: AsyncElasticsearch
    k: int = 10
    reranker: DocumentReranker = DocumentReranker()

    async def run(
        self,
        items: list[RetrievalEvaluationItem],
        approaches: list[RetrievalApproach],
    ) -> RetrievalEvaluationReport:
        """Evaluate every approach and select the highest-recall strategy."""
        if len(approaches) < 2:
            raise ValueError("Retrieval evaluation requires at least two approaches")
        results: list[RetrievalEvaluationResult] = []
        for item in items:
            for approach in approaches:
                results.append(await self._evaluate(item, approach))
        summary = self._summarize(results)
        return RetrievalEvaluationReport(
            results=results,
            summary=summary,
            best_approach=RetrievalApproach(summary[0]["approach"]),
        )

    async def _evaluate(
        self, item: RetrievalEvaluationItem, approach: RetrievalApproach
    ) -> RetrievalEvaluationResult:
        """Execute one search strategy and calculate ranking metrics."""
        try:
            filters = (
                [
                    {"match": {field: value}}
                    for field, value in item.filters.items()
                ]
                if approach is not RetrievalApproach.BM25
                else []
            )
            body: dict[str, Any] = {
                "bool": {
                    "must": [{"multi_match": {"query": item.query, "fields": ["label", "description", "ingredients", "categories"]}}],
                    "filter": filters,
                }
            }
            kwargs: dict[str, Any] = {
                "index": item.index,
                "size": self.reranker.candidate_size(self.k),
            }
            if approach in {
                RetrievalApproach.HYBRID,
                RetrievalApproach.HYBRID_RERANKED,
            } and item.embedding is not None:
                kwargs["retriever"] = {
                    "rrf": {
                        "retrievers": [
                            {"standard": {"query": body}},
                            {"knn": {"field": "embedding", "query_vector": item.embedding, "k": self.k, "num_candidates": 100}},
                        ],
                        "rank_window_size": self.k,
                    }
                }
            else:
                kwargs["query"] = body
            response = await self.client.search(**kwargs)
            hits = response["hits"]["hits"]
            if approach is RetrievalApproach.HYBRID_RERANKED:
                hits = self.reranker.rerank(hits, item.query, self.k)
            else:
                hits = hits[: self.k]
            retrieved = [str(hit["_id"]) for hit in hits]
            relevant = set(item.relevant_ids)
            rank = next((position for position, doc_id in enumerate(retrieved, 1) if doc_id in relevant), 0)
            return RetrievalEvaluationResult(
                approach=approach,
                index=item.index,
                query=item.query,
                retrieved_ids=retrieved,
                recall_at_k=len(set(retrieved) & relevant) / len(relevant),
                reciprocal_rank=1 / rank if rank else 0.0,
            )
        except Exception as error:
            return RetrievalEvaluationResult(
                approach=approach,
                index=item.index,
                query=item.query,
                retrieved_ids=[],
                recall_at_k=0.0,
                reciprocal_rank=0.0,
                error=str(error),
            )

    @staticmethod
    def _summarize(
        results: list[RetrievalEvaluationResult],
    ) -> list[dict[str, str | float | int]]:
        """Aggregate recall and MRR by strategy, best first."""
        summary = []
        for approach in RetrievalApproach:
            rows = [result for result in results if result.approach is approach]
            if not rows:
                continue
            summary.append({
                "approach": approach.value,
                "total": len(rows),
                "recall_at_k": sum(row.recall_at_k for row in rows) / len(rows),
                "mrr": sum(row.reciprocal_rank for row in rows) / len(rows),
            })
        return sorted(summary, key=lambda row: (row["recall_at_k"], row["mrr"]), reverse=True)


def load_dataset(path: Path) -> list[RetrievalEvaluationItem]:
    """Load and validate retrieval evaluation examples from JSON."""
    return [RetrievalEvaluationItem.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
