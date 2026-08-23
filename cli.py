"""Command-line interface for foodmind ingestion pipelines."""

import argparse

from app.ingestion.wikidata_food_entities import run_pipeline


def main() -> None:
    """Parse command-line options and run the Wikidata ingestion pipeline."""
    parser = argparse.ArgumentParser(
        description="Ingest normalized Wikidata food entities with dlt.",
    )
    parser.add_argument("--pipeline-name", default="wikidata_food_entities")
    parser.add_argument("--destination", default="duckdb")
    parser.add_argument("--dataset-name", default="foodmind")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--show-progress", action="store_true")
    args = parser.parse_args()

    load_info = run_pipeline(
        pipeline_name=args.pipeline_name,
        destination=args.destination,
        dataset_name=args.dataset_name,
        batch_size=args.batch_size,
        show_progress=args.show_progress,
    )
    print(load_info)


if __name__ == "__main__":
    main()
