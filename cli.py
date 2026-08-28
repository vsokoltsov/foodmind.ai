"""Command-line interface for foodmind ingestion pipelines."""

import argparse
import asyncio
from pathlib import Path

from app.ingestion.pipeline import IngestionConfig, run_ingestion
from app.settings import get_settings


def main() -> None:
    """Parse options and ingest every MVP source into Elasticsearch."""
    parser = argparse.ArgumentParser(
        description="Ingest all FoodMind MVP sources into Elasticsearch.",
    )
    parser.add_argument("--pipeline-name", default="wikidata_food_entities")
    parser.add_argument("--destination", default="duckdb")
    parser.add_argument("--dataset-name", default="foodmind")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--wikidata-batch-size", type=int, default=100)
    parser.add_argument(
        "--foundation-path",
        type=Path,
        default=Path("foundations.json.zip"),
    )
    parser.add_argument(
        "--branded-path",
        type=Path,
        default=Path("branded.json.zip"),
    )
    parser.add_argument(
        "--openfoodfacts-path",
        type=Path,
        default=Path("openfoodfacts-products.jsonl.gz"),
    )
    parser.add_argument("--show-progress", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    result = asyncio.run(
        run_ingestion(
            IngestionConfig(
                elasticsearch_url=settings.ELASTICSEARCH_URL,
                foundation_archive=args.foundation_path,
                branded_archive=args.branded_path,
                openfoodfacts_archive=args.openfoodfacts_path,
                repository_batch_size=args.batch_size,
                wikidata_batch_size=args.wikidata_batch_size,
                wikidata_pipeline_name=args.pipeline_name,
                wikidata_destination=args.destination,
                wikidata_dataset_name=args.dataset_name,
                show_progress=args.show_progress,
                force_download=args.force_download,
            )
        )
    )
    for source in result.sources:
        print(f"{source.source}: {source.records_indexed:,} records indexed")
    print(f"total: {result.total_records_indexed:,} records indexed")


if __name__ == "__main__":
    main()
