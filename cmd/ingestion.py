"""Command-line interface for FoodMind ingestion pipelines."""

import argparse
import asyncio
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

import structlog

# Running this file directly puts ``cmd/`` rather than the repository root on
# sys.path. Add the root so the application package remains importable.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pipeline import IngestionConfig, run_ingestion
from app.ingestion.staged import (
    SourceName,
    StagedIngestionConfig,
    download_source,
    extract_wikidata_base,
    extract_wikidata_details,
    extract_wikidata_normalized,
    index_staged_source,
    load_pending,
    materialize_source,
    normalize_pending,
    process_source_batches,
    validate_staged_source,
)
from app.observability.structured_logging import configure_structlog
from app.settings import get_settings

SOURCES: tuple[SourceName, ...] = (
    "wikidata",
    "usda-foundation",
    "usda-branded",
    "openfoodfacts",
)
WIKIDATA_STAGES = (
    "extract-base",
    "normalize-base",
    "load-base",
    "extract-details",
    "normalize-details",
    "load-details",
    "transform",
    "normalize-final",
    "load-final",
    "index",
    "validate",
)
ARCHIVE_STAGES = (
    "download",
    "process",
    "index",
    "validate",
)


def configure_structured_logging() -> None:
    """Emit structured ingestion events to the task pod's standard output."""
    configure_structlog()


def _legacy_parser() -> argparse.ArgumentParser:
    """Build the backwards-compatible all-sources CLI parser."""
    parser = argparse.ArgumentParser(
        description="Ingest all FoodMind MVP sources into Elasticsearch.",
    )
    parser.add_argument("--pipeline-name", default="wikidata_food_entities")
    parser.add_argument("--destination", default="duckdb")
    parser.add_argument("--dataset-name", default="foodmind")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--source-batch-size", type=int, default=25_000)
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
    return parser


def _stage_parser() -> argparse.ArgumentParser:
    """Build the parser used by independently executable Kestra stages."""
    parser = argparse.ArgumentParser(description="Run one durable ingestion stage.")
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("stage")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--source-batch-size", type=int, default=25_000)
    parser.add_argument("--wikidata-batch-size", type=int, default=100)
    parser.add_argument(
        "--foundation-path", type=Path, default=Path("foundations.json.zip")
    )
    parser.add_argument("--branded-path", type=Path, default=Path("branded.json.zip"))
    parser.add_argument(
        "--openfoodfacts-path",
        type=Path,
        default=Path("openfoodfacts-products.jsonl.gz"),
    )
    parser.add_argument("--pipelines-dir", type=Path, default=Path(".dlt/pipelines"))
    parser.add_argument("--staging-dir", type=Path, default=Path(".dlt/staging"))
    parser.add_argument("--normalized-dir", type=Path, default=Path(".dlt/normalized"))
    parser.add_argument("--show-progress", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    return parser


def _stage_config(args: argparse.Namespace) -> StagedIngestionConfig:
    """Create stage configuration from command-line arguments and settings."""
    return StagedIngestionConfig(
        elasticsearch_url=get_settings().ELASTICSEARCH_URL,
        foundation_archive=args.foundation_path,
        branded_archive=args.branded_path,
        openfoodfacts_archive=args.openfoodfacts_path,
        pipelines_dir=args.pipelines_dir,
        staging_dir=args.staging_dir,
        normalized_dir=args.normalized_dir,
        repository_batch_size=args.batch_size,
        source_batch_size=args.source_batch_size,
        wikidata_batch_size=args.wikidata_batch_size,
        show_progress=args.show_progress,
        force_download=args.force_download,
        artifact_storage=get_settings().INGESTION_ARTIFACT_STORAGE,
        gcs_bucket=get_settings().GCS_BUCKET,
        gcs_prefix=get_settings().GCS_PREFIX,
        gcp_project_id=get_settings().GCP_PROJECT_ID,
    )


async def _run_stage(
    source: SourceName,
    stage: str,
    config: StagedIngestionConfig,
) -> Any:
    """Dispatch one source stage while keeping blocking dlt work off-loop."""
    allowed = WIKIDATA_STAGES if source == "wikidata" else ARCHIVE_STAGES
    if stage not in allowed:
        raise ValueError(
            f"Invalid stage {stage!r} for {source}; expected one of {allowed}"
        )
    logger = structlog.get_logger(__name__)
    logger.info(
        "ingestion_stage_started",
        source=source,
        stage=stage,
        pipelines_dir=str(config.pipelines_dir),
        staging_dir=str(config.staging_dir),
    )
    started_at = perf_counter()
    try:
        if stage == "download":
            result = await download_source(source, config)
        elif stage == "extract-base":
            result = await asyncio.to_thread(extract_wikidata_base, config)
        elif stage == "extract-details":
            result = await asyncio.to_thread(extract_wikidata_details, config)
        elif stage == "transform" and source == "wikidata":
            result = await asyncio.to_thread(extract_wikidata_normalized, config)
        elif stage == "process":
            await materialize_source(source, config)
            result = await asyncio.to_thread(process_source_batches, source, config)
        elif stage.startswith("normalize") or stage == "normalize":
            result = await asyncio.to_thread(normalize_pending, source, config)
        elif stage.startswith("load") or stage == "load":
            result = await asyncio.to_thread(load_pending, source, config)
        elif stage == "index":
            result = await index_staged_source(source, config)
        elif stage == "validate":
            result = await validate_staged_source(source, config)
        else:
            raise AssertionError(f"Unhandled stage: {stage}")
    except Exception:
        logger.exception("ingestion_stage_failed", source=source, stage=stage)
        raise
    logger.info(
        "ingestion_stage_completed",
        source=source,
        stage=stage,
        elapsed_seconds=round(perf_counter() - started_at, 1),
        result=str(result),
    )
    return result


def _run_all(args: argparse.Namespace) -> None:
    """Run the original all-sources ingestion entry point."""

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
                artifact_storage=settings.INGESTION_ARTIFACT_STORAGE,
                gcs_bucket=settings.GCS_BUCKET,
                gcs_prefix=settings.GCS_PREFIX,
                gcp_project_id=settings.GCP_PROJECT_ID,
            )
        )
    )
    for source in result.sources:
        print(f"{source.source}: {source.records_indexed:,} records indexed")
    print(f"total: {result.total_records_indexed:,} records indexed")


def main() -> None:
    """Run either one Kestra stage or the backwards-compatible full ingestion."""
    configure_structured_logging()
    if len(sys.argv) > 1 and sys.argv[1] == "stage":
        args = _stage_parser().parse_args(sys.argv[2:])
        result = asyncio.run(_run_stage(args.source, args.stage, _stage_config(args)))
        print(f"{args.source}.{args.stage}: completed")
        if args.stage == "validate":
            print(f"staging={result[0]}, elasticsearch={result[1]}")
        elif args.stage in {"download", "index"}:
            print(result)
        return
    _run_all(_legacy_parser().parse_args())


if __name__ == "__main__":
    main()
