"""Run LLM-as-judge evaluation for the food-search agent."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from elasticsearch import AsyncElasticsearch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.foodmind import _create_model
from app.agents.food_search import FoodSearchDependencies
from app.evaluation.food_search import (
    FoodSearchApproach,
    FoodSearchEvaluationRunner,
    FoodSearchJudge,
    load_dataset,
    summarize_results,
)
from app.settings import get_settings


async def run(dataset: Path, limit: int | None) -> list[dict[str, str | int | float]]:
    """Run both approaches and return their judge score summary.

    Args:
        dataset: Ground-truth JSON dataset path.
        limit: Optional maximum number of examples.

    Returns:
        Per-approach evaluation summary, best approach first.
    """
    settings = get_settings()
    items = load_dataset(dataset)
    if limit is not None:
        items = items[:limit]
    async with AsyncElasticsearch(settings.ELASTICSEARCH_URL) as client:
        runner = FoodSearchEvaluationRunner(
            dependencies=FoodSearchDependencies.from_client(client),
            judge=FoodSearchJudge(_create_model()),
        )
        results = await runner.run(
            items,
            [FoodSearchApproach.DIRECT, FoodSearchApproach.EVIDENCE_FIRST],
        )
    return summarize_results(results)


def main() -> None:
    """Parse arguments, run evaluation, and print JSON results."""
    parser = argparse.ArgumentParser(description="Evaluate the FoodMind search agent.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parents[1] / "app/evaluation/food_search_dataset.json",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    summary = asyncio.run(run(args.dataset, args.limit))
    print(
        json.dumps(
            {
                "best_approach": summary[0]["approach"] if summary else None,
                "summary": summary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
