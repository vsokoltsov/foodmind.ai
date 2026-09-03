"""Elasticsearch retrieval-quality evaluation."""

import asyncio
import json
from pathlib import Path

import pytest

from app.evaluation.retrieval import (
    RetrievalApproach,
    RetrievalEvaluationItem,
    RetrievalEvaluationRunner,
    load_dataset,
)
from app.evaluation.artifacts import EvaluationArtifactRepository


def test_retrieval_dataset_is_validated() -> None:
    """Retrieval examples require at least one relevant document."""
    with pytest.raises(ValueError):
        RetrievalEvaluationItem.model_validate({"index": "foods", "query": "apple", "relevant_ids": []})


@pytest.mark.evaluation
def test_retrieval_evaluation(evaluation_catalog: str, tmp_path: Path) -> None:
    """Compare retrieval approaches and persist the selected strategy."""
    from elasticsearch import AsyncElasticsearch

    async def evaluate() -> object:
        client = AsyncElasticsearch(evaluation_catalog)
        try:
            runner = RetrievalEvaluationRunner(client)
            return await runner.run(
                load_dataset(Path(__file__).parent / "retrieval_dataset.json"),
                [
                    RetrievalApproach.BM25,
                    RetrievalApproach.FILTERED_BM25,
                    RetrievalApproach.HYBRID_RERANKED,
                ],
            )
        finally:
            await client.close()

    report = asyncio.run(evaluate())
    output = tmp_path / "retrieval-results.json"
    report.save(output)
    asyncio.run(
        EvaluationArtifactRepository().save(
            "retrieval", report.summary, report.best_approach.value
        )
    )
    assert output.exists()
    assert report.best_approach in {
        RetrievalApproach.BM25,
        RetrievalApproach.FILTERED_BM25,
    }
    assert len(json.loads(output.read_text())["results"]) == 63
