"""Durable, independently executable ingestion stages for Kestra."""

import json
import re
import sqlite3
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, get_args, get_origin

import dlt
import gcsfs
import httpx
import structlog
from elasticsearch import AsyncElasticsearch
from pydantic import BaseModel, Field
from pyarrow import parquet

from app.clients.openfoodfacts.client import OpenFoodFactsClient
from app.clients.openfoodfacts.reader import OpenFoodFactsReader
from app.clients.usda_fdc.client import USDAFoundationClient
from app.clients.usda_fdc.reader import USDAFoodDataReader
from app.aggregates import (
    BrandedFood as BrandedFoodAggregate,
    FoodEntity,
    FoundationFood as FoundationFoodAggregate,
    OpenFoodFactsProduct as OpenFoodFactsAggregate,
)
from app.ingestion.elasticsearch_snapshots import (
    pending_snapshot_index,
    prepare_snapshot_index,
    publish_snapshot_index,
)
from app.ingestion.models import (
    WikidataAliasRecord,
    WikidataEntityRecord,
    WikidataMediaArticleRecord,
    WikidataOriginRecord,
    WikidataTaxonomyRecord,
)
from app.ingestion.pipeline import index_records
from app.ingestion.wikidata_food_entities import (
    normalize_food_entity_records,
    normalized_food_entities_resource,
    wikidata_details_source,
    wikidata_entities_resource,
)
from app.repositories.openfoodfacts import OpenFoodFactsRepository
from app.repositories.usda import USDARepository
from app.repositories.wikidata import WikidataFoodRepository
from app.storage.factory import create_artifact_store as build_artifact_store
from app.storage.protocol import ArtifactStore

SourceName = Literal[
    "wikidata",
    "usda-foundation",
    "usda-branded",
    "openfoodfacts",
]
ModelT = TypeVar("ModelT", bound=BaseModel)
JSON_CONTAINER_TYPES = (list, dict, tuple, set, frozenset)
NORMALIZATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StagedIngestionConfig:
    """Paths and runtime options shared by independently executed stages."""

    elasticsearch_url: str = "http://localhost:9200"
    foundation_archive: Path = Path("foundations.json.zip")
    branded_archive: Path = Path("branded.json.zip")
    openfoodfacts_archive: Path = Path("openfoodfacts-products.jsonl.gz")
    pipelines_dir: Path = Path(".dlt/pipelines")
    staging_dir: Path = Path(".dlt/staging")
    normalized_dir: Path = Path(".dlt/normalized")
    repository_batch_size: int = 500
    source_batch_size: int = 25_000
    wikidata_batch_size: int = 100
    show_progress: bool = False
    force_download: bool = False
    artifact_storage: Literal["local", "gcs"] = "local"
    gcs_bucket: str | None = None
    gcs_prefix: str = "foodmind/ingestion"
    gcp_project_id: str | None = None

    def __post_init__(self) -> None:
        """Reject invalid batch sizes before a stage mutates state."""
        if self.repository_batch_size < 1:
            raise ValueError("repository_batch_size must be at least 1")
        if self.source_batch_size < 1:
            raise ValueError("source_batch_size must be at least 1")
        if self.wikidata_batch_size < 1:
            raise ValueError("wikidata_batch_size must be at least 1")


PIPELINE_NAMES: dict[SourceName, str] = {
    "wikidata": "wikidata_food_entities",
    "usda-foundation": "usda_foundation_foods",
    "usda-branded": "usda_branded_foods",
    "openfoodfacts": "openfoodfacts_products",
}
TABLES: dict[SourceName, str] = {
    "wikidata": "food_entities",
    "usda-foundation": "usda_foundation_documents",
    "usda-branded": "usda_branded_documents",
    "openfoodfacts": "openfoodfacts_documents",
}
INDEX_ALIASES: dict[SourceName, str] = {
    "wikidata": "wikidata-food-entities",
    "usda-foundation": "usda-foundation-foods",
    "usda-branded": "usda-branded-foods",
    "openfoodfacts": "openfoodfacts-products",
}


class ParquetBatchCheckpoint(BaseModel):
    """One completely committed source batch and its immutable Parquet objects."""

    number: int
    rows: int
    files: list[str]


class ElasticsearchCheckpoint(BaseModel):
    """Resumable Elasticsearch snapshot progress for one source generation."""

    candidate_index: str | None = None
    completed_files: list[str] = Field(default_factory=list)
    indexed_records: int = 0
    published: bool = False


class IngestionManifest(BaseModel):
    """Durable source-generation manifest shared by independent Kestra pods."""

    schema_version: int = 1
    normalization_version: int = NORMALIZATION_SCHEMA_VERSION
    source: SourceName
    source_version: str
    source_size: int
    run_id: str
    source_batch_size: int
    batches: list[ParquetBatchCheckpoint] = Field(default_factory=list)
    processing_complete: bool = False
    total_rows: int = 0
    elasticsearch: ElasticsearchCheckpoint = Field(
        default_factory=ElasticsearchCheckpoint
    )


def _gcs_filesystem(config: StagedIngestionConfig) -> gcsfs.GCSFileSystem:
    """Create the authenticated filesystem used for source, state, and Parquet."""
    return gcsfs.GCSFileSystem(project=config.gcp_project_id)


def _state_path(source: SourceName, config: StagedIngestionConfig) -> Path | str:
    """Return the durable current-run manifest path for a source."""
    relative = f"checkpoints/{source}/manifest.json"
    if config.artifact_storage == "gcs":
        if not config.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for durable ingestion state")
        prefix = "/".join(
            part for part in (config.gcs_prefix.strip("/"), relative) if part
        )
        return f"{config.gcs_bucket}/{prefix}"
    return config.staging_dir / ".ingestion-manifests" / source / "manifest.json"


def _archived_state_path(
    manifest: IngestionManifest, config: StagedIngestionConfig
) -> Path | str:
    """Return the run-scoped audit path for one normalization manifest."""
    relative = f"checkpoints/{manifest.source}/runs/{manifest.run_id}.json"
    if config.artifact_storage == "gcs":
        if not config.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for durable ingestion state")
        prefix = "/".join(
            part for part in (config.gcs_prefix.strip("/"), relative) if part
        )
        return f"{config.gcs_bucket}/{prefix}"
    return (
        config.staging_dir
        / ".ingestion-manifests"
        / manifest.source
        / "runs"
        / (f"{manifest.run_id}.json")
    )


def _read_manifest(
    source: SourceName, config: StagedIngestionConfig
) -> IngestionManifest | None:
    """Read the current source manifest from GCS or the local staging directory."""
    path = _state_path(source, config)
    if isinstance(path, Path):
        if not path.exists():
            return None
        return IngestionManifest.model_validate_json(path.read_text(encoding="utf-8"))
    filesystem = _gcs_filesystem(config)
    if not filesystem.exists(path):
        return None
    return IngestionManifest.model_validate_json(filesystem.cat(path))


def _write_manifest(manifest: IngestionManifest, config: StagedIngestionConfig) -> None:
    """Persist current and run-scoped manifests after a completed work unit."""
    path = _state_path(manifest.source, config)
    archived_path = _archived_state_path(manifest, config)
    payload = manifest.model_dump_json(indent=2).encode()
    if isinstance(path, Path):
        for destination in (path, archived_path):
            assert isinstance(destination, Path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(destination)
        return
    filesystem = _gcs_filesystem(config)
    filesystem.pipe(archived_path, payload)
    filesystem.pipe(path, payload)


def _source_identity(
    source: SourceName, config: StagedIngestionConfig
) -> tuple[str, int, str]:
    """Return a stable source version, byte size, and path-safe run identifier."""
    path = {
        "usda-foundation": config.foundation_archive,
        "usda-branded": config.branded_archive,
        "openfoodfacts": config.openfoodfacts_archive,
    }.get(source)
    if path is None:
        raise ValueError("Wikidata does not use archive generation manifests")
    if config.artifact_storage == "gcs":
        object_path = _artifact_gcs_object(source, path, config)
        info = _gcs_filesystem(config).info(object_path)
        version = str(
            info.get("generation")
            or info.get("etag")
            or info.get("md5Hash")
            or f"{info.get('size', 0)}-{info.get('updated', 'unknown')}"
        )
        size = int(info.get("size", 0))
    else:
        stat = path.stat()
        version = f"{stat.st_size}-{stat.st_mtime_ns}"
        size = stat.st_size
    run_id = re.sub(r"[^a-zA-Z0-9_-]", "-", version).strip("-")[:80]
    if not run_id:
        raise RuntimeError(f"Could not derive a run identifier for {source}")
    return version, size, run_id


def _load_or_create_manifest(
    source: SourceName, config: StagedIngestionConfig
) -> IngestionManifest:
    """Select a manifest by immutable source version, starting a new run if needed."""
    version, size, source_run_id = _source_identity(source, config)
    manifest = _read_manifest(source, config)
    if (
        manifest is not None
        and manifest.source_version == version
        and manifest.source_batch_size == config.source_batch_size
        and manifest.normalization_version == NORMALIZATION_SCHEMA_VERSION
    ):
        return manifest
    run_id = (
        f"{source_run_id}-b{config.source_batch_size}-n{NORMALIZATION_SCHEMA_VERSION}"
    )
    manifest = IngestionManifest(
        source=source,
        source_version=version,
        source_size=size,
        run_id=run_id,
        source_batch_size=config.source_batch_size,
    )
    _write_manifest(manifest, config)
    return manifest


def _require_current_manifest(
    source: SourceName, config: StagedIngestionConfig
) -> IngestionManifest:
    """Return a completed manifest that still matches the current source object."""
    manifest = _read_manifest(source, config)
    if manifest is None:
        raise RuntimeError(f"No durable ingestion manifest exists for {source}")
    version, _size, _run_id = _source_identity(source, config)
    if manifest.source_version != version:
        raise RuntimeError(
            f"The {source} source generation changed after Parquet processing; "
            "run the process stage for the new generation before indexing"
        )
    if not manifest.processing_complete:
        raise RuntimeError(f"Parquet processing is incomplete for {source}")
    return manifest


def artifact_key(source: SourceName, path: Path) -> str:
    """Return the stable object key used for one source archive."""
    return f"{source}/{path.name}"


def create_artifact_store(config: StagedIngestionConfig) -> ArtifactStore:
    """Create the configured local or GCS artifact backend."""
    return build_artifact_store(
        config.artifact_storage,
        bucket=config.gcs_bucket,
        prefix=config.gcs_prefix,
        project=config.gcp_project_id,
    )


def create_pipeline(
    source: SourceName,
    config: StagedIngestionConfig,
    *,
    run_id: str | None = None,
) -> Any:
    """Create one dlt pipeline with a durable Parquet destination.

    The filesystem destination writes Parquet directly to GCS through
    ``gcsfs``. A completed ``pipeline.run`` therefore leaves a durable load
    package behind even when the Kubernetes task pod is interrupted. The dlt
    working state may be ephemeral because the durable manifest records every
    completed batch and Elasticsearch file checkpoint outside the task pod.
    """
    config.pipelines_dir.mkdir(parents=True, exist_ok=True)
    config.staging_dir.mkdir(parents=True, exist_ok=True)
    config.normalized_dir.mkdir(parents=True, exist_ok=True)
    pipeline_name = PIPELINE_NAMES[source]
    if source != "wikidata" and config.artifact_storage == "gcs":
        if not config.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for GCS-backed dlt ingestion")
        run_prefix = f"/runs/{source}/{run_id}" if run_id is not None else ""
        destination = dlt.destinations.filesystem(
            bucket_url=(
                f"gs://{config.gcs_bucket}/"
                f"{config.gcs_prefix.strip('/')}/dlt-normalized{run_prefix}"
            )
        )
    elif source != "wikidata":
        destination_path = config.normalized_dir
        if run_id is not None:
            destination_path /= f"runs/{source}/{run_id}"
        destination = dlt.destinations.filesystem(bucket_url=str(destination_path))
    else:
        destination = dlt.destinations.duckdb(
            credentials=str(config.staging_dir / f"{pipeline_name}.duckdb")
        )
    return dlt.pipeline(
        pipeline_name=pipeline_name,
        pipelines_dir=str(config.pipelines_dir),
        destination=destination,
        dataset_name=f"{pipeline_name}_data",
    )


def _file_size_megabytes(path: Path) -> float:
    """Return a local file size for concise ingestion progress logs."""
    return path.stat().st_size / (1024 * 1024)


@contextmanager
def source_pipeline_lock(
    source: SourceName, config: StagedIngestionConfig
) -> Iterator[None]:
    """Acquire an exclusive non-blocking lock for one source dlt pipeline.

    This process-local guard rejects duplicate workers that share a filesystem.
    Kestra's per-source concurrency limit supplies the cluster-wide guard,
    while the GCS manifest supplies durable restart state across task pods.
    """
    import fcntl

    config.pipelines_dir.mkdir(parents=True, exist_ok=True)
    lock_path = config.pipelines_dir / f".{PIPELINE_NAMES[source]}.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"The {source} ingestion pipeline is already running; "
                "wait for the active Kestra stage before retrying."
            ) from error
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def usda_foundation_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Foundation Foods into canonical documents."""
    for food in USDAFoodDataReader().iter_foundation_foods(path):
        yield food.to_domain().model_dump(mode="json")


def usda_branded_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Branded Foods into canonical documents."""
    for food in USDAFoodDataReader().iter_branded_foods(path):
        yield food.to_domain().model_dump(mode="json")


def usda_gcs_documents_resource(
    source: SourceName, config: StagedIngestionConfig
) -> Iterator[dict[str, Any]]:
    """Stream and validate a USDA ZIP directly from its durable GCS object."""
    path = (
        config.foundation_archive
        if source == "usda-foundation"
        else config.branded_archive
    )
    object_path = _artifact_gcs_object(source, path, config)
    filesystem = _gcs_filesystem(config)
    reader = USDAFoodDataReader()
    with filesystem.open(object_path, "rb") as compressed_export:
        foods = (
            reader.iter_foundation_foods_stream(
                compressed_export, source_name=f"gs://{object_path}"
            )
            if source == "usda-foundation"
            else reader.iter_branded_foods_stream(
                compressed_export, source_name=f"gs://{object_path}"
            )
        )
        for food in foods:
            yield food.to_domain().model_dump(mode="json")


def openfoodfacts_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Open Food Facts products into canonical documents."""
    for product in OpenFoodFactsReader().iter_products(path):
        yield product.to_domain().model_dump(mode="json")


def _artifact_gcs_object(
    source: SourceName,
    path: Path,
    config: StagedIngestionConfig,
) -> str:
    """Return the GCS object path for one archive source."""
    if not config.gcs_bucket:
        raise ValueError("GCS_BUCKET is required for GCS-backed ingestion")
    key = artifact_key(source, path)
    prefix = "/".join(part for part in (config.gcs_prefix.strip("/"), key) if part)
    return f"{config.gcs_bucket}/{prefix}"


def openfoodfacts_gcs_documents_resource(
    config: StagedIngestionConfig,
) -> Iterator[dict[str, Any]]:
    """Stream a compressed Open Food Facts archive directly from GCS."""
    object_path = _artifact_gcs_object(
        "openfoodfacts", config.openfoodfacts_archive, config
    )
    filesystem = _gcs_filesystem(config)
    with filesystem.open(object_path, "rb") as compressed_export:
        for product in OpenFoodFactsReader().iter_products_stream(
            compressed_export,
            source_name=f"gs://{object_path}",
        ):
            yield product.to_domain().model_dump(mode="json")


ARCHIVE_MODELS: dict[SourceName, type[BaseModel]] = {
    "usda-foundation": FoundationFoodAggregate,
    "usda-branded": BrandedFoodAggregate,
    "openfoodfacts": OpenFoodFactsAggregate,
}


def _archive_documents(
    source: SourceName, config: StagedIngestionConfig
) -> Iterator[dict[str, Any]]:
    """Yield canonical documents for one archive-backed source."""
    match source:
        case "usda-foundation":
            if config.artifact_storage == "gcs":
                yield from usda_gcs_documents_resource(source, config)
            else:
                yield from usda_foundation_documents_resource(config.foundation_archive)
        case "usda-branded":
            if config.artifact_storage == "gcs":
                yield from usda_gcs_documents_resource(source, config)
            else:
                yield from usda_branded_documents_resource(config.branded_archive)
        case "openfoodfacts":
            if config.artifact_storage == "gcs":
                yield from openfoodfacts_gcs_documents_resource(config)
            else:
                yield from openfoodfacts_documents_resource(
                    config.openfoodfacts_archive
                )
        case _:
            raise ValueError("Wikidata uses its dedicated extraction stages")


def _document_batches(
    documents: Iterator[dict[str, Any]], batch_size: int
) -> Iterator[list[dict[str, Any]]]:
    """Split a document stream without materialising the full source export."""
    batch: list[dict[str, Any]] = []
    for document in documents:
        batch.append(document)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _batch_resource(source: SourceName, documents: list[dict[str, Any]]) -> Any:
    """Build one append-only Parquet dlt resource from a bounded batch."""
    return dlt.resource(
        documents,
        name=TABLES[source],
        primary_key="id",
        write_disposition="append",
        columns=ARCHIVE_MODELS[source],
        file_format="parquet",
    )


def _discard_incompatible_legacy_pending_packages(
    source: SourceName, config: StagedIngestionConfig, pipeline: Any
) -> None:
    """Remove pending DuckDB jobs left behind before the Parquet migration.

    Archive pipelines used DuckDB before they were changed to the filesystem
    destination.  A pending ``insert_values.gz`` job cannot be loaded by the
    filesystem destination and prevents dlt from starting a new Parquet run.
    This is deliberately narrow: it only removes *all* pending packages when
    every pending job is legacy.  A mixed legacy/Parquet state needs operator
    review instead of risking deletion of new durable work.
    """
    load_directory = config.pipelines_dir / PIPELINE_NAMES[source] / "load"
    legacy_jobs = list(load_directory.glob("**/*.insert_values.gz"))
    if not legacy_jobs:
        return

    parquet_jobs = list(load_directory.glob("**/*.parquet"))
    if parquet_jobs:
        raise RuntimeError(
            "The dlt pipeline contains both legacy DuckDB and Parquet pending "
            "packages. Resolve the pending packages before retrying ingestion."
        )

    structlog.get_logger(__name__).warning(
        "dlt_destination_migration_discarded_legacy_pending_packages",
        source=source,
        legacy_job_count=len(legacy_jobs),
    )
    pipeline.drop_pending_packages()


def process_source_batches(source: SourceName, config: StagedIngestionConfig) -> int:
    """Write an archive to durable Parquet through small recoverable dlt runs.

    Each call to ``pipeline.run`` commits one source batch to a source-versioned
    Parquet destination. The durable manifest, rather than local dlt state or a
    guessed file count, identifies the committed batches and their exact files.
    """
    if source == "wikidata":
        raise ValueError("Wikidata uses its dedicated staged flow")
    with source_pipeline_lock(source, config):
        logger = structlog.get_logger(__name__)
        manifest = _load_or_create_manifest(source, config)
        if manifest.processing_complete:
            logger.info(
                "dlt_parquet_source_already_complete",
                source=source,
                run_id=manifest.run_id,
                total_rows=manifest.total_rows,
                completed_batches=len(manifest.batches),
            )
            return 0
        pipeline = create_pipeline(source, config, run_id=manifest.run_id)
        _discard_incompatible_legacy_pending_packages(source, config, pipeline)
        checkpoints = {batch.number: batch for batch in manifest.batches}
        logger.info(
            "dlt_parquet_batch_processing_started",
            source=source,
            run_id=manifest.run_id,
            source_version=manifest.source_version,
            source_batch_size=config.source_batch_size,
            completed_batches=len(checkpoints),
        )
        processed_records = 0
        for batch_number, documents in enumerate(
            _document_batches(
                _archive_documents(source, config), config.source_batch_size
            ),
            start=1,
        ):
            checkpoint = checkpoints.get(batch_number)
            if checkpoint is not None:
                if checkpoint.rows != len(documents):
                    raise RuntimeError(
                        f"Checkpoint batch {batch_number} has {checkpoint.rows} rows, "
                        f"but the current source produced {len(documents)}"
                    )
                logger.info(
                    "dlt_parquet_batch_skipped",
                    source=source,
                    batch_number=batch_number,
                    records_in_batch=len(documents),
                    completed_batches=len(manifest.batches),
                    remaining_batches="unknown_until_source_end",
                )
                continue
            claimed_files = {path for batch in manifest.batches for path in batch.files}
            unclaimed_files = [
                str(path)
                for path in _discover_parquet_paths(source, config, manifest.run_id)
                if str(path) not in claimed_files
            ]
            if unclaimed_files:
                orphan_rows = _parquet_row_count(unclaimed_files, config)
                if orphan_rows != len(documents):
                    raise RuntimeError(
                        "Unclaimed Parquet files do not match the next source batch; "
                        f"expected {len(documents)} rows and found {orphan_rows}. "
                        "Start a new source generation or inspect the run prefix."
                    )
                new_files = unclaimed_files
                logger.warning(
                    "dlt_parquet_batch_recovered_from_uncommitted_manifest",
                    source=source,
                    batch_number=batch_number,
                    files=new_files,
                )
            else:
                before = {
                    str(path)
                    for path in _discover_parquet_paths(source, config, manifest.run_id)
                }
                pipeline.run(_batch_resource(source, documents))
                new_files = [
                    str(path)
                    for path in _discover_parquet_paths(source, config, manifest.run_id)
                    if str(path) not in before
                ]
                if not new_files:
                    raise RuntimeError(
                        f"dlt completed batch {batch_number} without creating Parquet"
                    )
                written_rows = _parquet_row_count(new_files, config)
                if written_rows != len(documents):
                    raise RuntimeError(
                        f"dlt wrote {written_rows} rows for a {len(documents)}-row batch"
                    )
            batch_checkpoint = ParquetBatchCheckpoint(
                number=batch_number,
                rows=len(documents),
                files=new_files,
            )
            manifest.batches.append(batch_checkpoint)
            manifest.total_rows += len(documents)
            _write_manifest(manifest, config)
            processed_records += len(documents)
            logger.info(
                "dlt_parquet_batch_completed",
                source=source,
                batch_number=batch_number,
                records_in_batch=len(documents),
                records_processed=processed_records,
                total_durable_records=manifest.total_rows,
                completed_batches=len(manifest.batches),
                remaining_batches="unknown_until_source_end",
                durable_files=len(new_files),
            )
        manifest.processing_complete = True
        _write_manifest(manifest, config)
        logger.info(
            "dlt_parquet_batch_processing_completed",
            source=source,
            newly_processed_records=processed_records,
            completed_batches=len(manifest.batches),
            total_rows=manifest.total_rows,
        )
        return processed_records


def extract_wikidata_base(config: StagedIngestionConfig) -> Any:
    """Extract Wikidata base entities without normalizing or loading them."""
    return create_pipeline("wikidata", config).extract(wikidata_entities_resource())


def extract_wikidata_details(config: StagedIngestionConfig) -> Any:
    """Extract all four Wikidata detail resources for loaded base entity IDs."""
    pipeline = create_pipeline("wikidata", config)
    entities = list(iter_models(pipeline, "wikidata_entities", WikidataEntityRecord))
    qids = [f"wd:{entity.id}" for entity in entities]
    if not qids:
        return None
    return pipeline.extract(
        wikidata_details_source(
            qids,
            batch_size=config.wikidata_batch_size,
            show_progress=config.show_progress,
        )
    )


def extract_wikidata_normalized(config: StagedIngestionConfig) -> Any:
    """Join loaded Wikidata staging tables into the final pending resource."""
    pipeline = create_pipeline("wikidata", config)
    records = normalize_food_entity_records(
        list(iter_models(pipeline, "wikidata_entities", WikidataEntityRecord)),
        list(iter_models(pipeline, "wikidata_aliases", WikidataAliasRecord)),
        list(iter_models(pipeline, "wikidata_taxonomy", WikidataTaxonomyRecord)),
        list(iter_models(pipeline, "wikidata_origins", WikidataOriginRecord)),
        list(
            iter_models(
                pipeline,
                "wikidata_media_articles",
                WikidataMediaArticleRecord,
            )
        ),
    )
    return pipeline.extract(normalized_food_entities_resource(records))


def normalize_pending(source: SourceName, config: StagedIngestionConfig) -> Any:
    """Normalize all extracted packages waiting in one source pipeline."""
    with source_pipeline_lock(source, config):
        pipeline = create_pipeline(source, config)
        packages = pipeline.list_extracted_load_packages()
        logger = structlog.get_logger(__name__)
        logger.info(
            "dlt_normalization_started",
            source=source,
            package_count=len(packages),
        )
        result = pipeline.normalize()
        logger.info("dlt_normalization_completed", source=source)
        return result


def load_pending(source: SourceName, config: StagedIngestionConfig) -> Any:
    """Load all normalized packages into one source's DuckDB staging database."""
    with source_pipeline_lock(source, config):
        pipeline = create_pipeline(source, config)
        packages = pipeline.list_normalized_load_packages()
        logger = structlog.get_logger(__name__)
        logger.info(
            "dlt_load_started",
            source=source,
            package_count=len(packages),
        )
        result = pipeline.load()
        logger.info("dlt_load_completed", source=source)
        return result


def _expects_json_value(annotation: Any) -> bool:
    """Return whether a Pydantic annotation represents structured JSON."""
    origin = get_origin(annotation)
    if annotation in JSON_CONTAINER_TYPES or origin in JSON_CONTAINER_TYPES:
        return True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return any(_expects_json_value(argument) for argument in get_args(annotation))


def _model_from_row(
    columns: list[str],
    row: tuple[Any, ...],
    model: type[ModelT],
) -> ModelT:
    """Restore dlt JSON columns and validate one staging row."""
    values = dict(zip(columns, row))
    for column, value in values.items():
        if (
            isinstance(value, str)
            and value.startswith(("[", "{"))
            and _expects_json_value(model.model_fields[column].annotation)
        ):
            values[column] = json.loads(value)
    return model.model_validate(values)


def iter_models(
    pipeline: Any,
    table_name: str,
    model: type[ModelT],
    *,
    fetch_size: int = 1_000,
) -> Iterator[ModelT]:
    """Stream a dlt staging table into validated models in bounded chunks."""
    columns = list(model.model_fields)
    relation = pipeline.dataset().table(table_name).select(*columns)
    for rows in relation.iter_fetch(fetch_size):
        for row in rows:
            yield _model_from_row(columns, row, model)


def _discover_parquet_paths(
    source: SourceName,
    config: StagedIngestionConfig,
    run_id: str,
) -> list[Path | str]:
    """Discover Parquet objects inside one immutable source-generation prefix."""
    pipeline_name = PIPELINE_NAMES[source]
    if config.artifact_storage == "gcs":
        if not config.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for GCS-backed dlt ingestion")
        prefix = "/".join(
            (
                config.gcs_prefix.strip("/"),
                "dlt-normalized",
                "runs",
                source,
                run_id,
                f"{pipeline_name}_data",
                TABLES[source],
                "*.parquet",
            )
        )
        filesystem = _gcs_filesystem(config)
        return sorted(filesystem.glob(f"{config.gcs_bucket}/{prefix}"))
    table_dir = (
        config.normalized_dir
        / "runs"
        / source
        / run_id
        / f"{pipeline_name}_data"
        / TABLES[source]
    )
    return sorted(table_dir.glob("*.parquet")) if table_dir.exists() else []


def _parquet_paths(
    source: SourceName, config: StagedIngestionConfig
) -> list[Path | str]:
    """Return only the Parquet files committed in the durable current manifest."""
    manifest = _read_manifest(source, config)
    if manifest is None:
        return []
    return [path for batch in manifest.batches for path in batch.files]


def _parquet_file(
    path: Path | str,
    config: StagedIngestionConfig,
    *,
    filesystem: gcsfs.GCSFileSystem | None = None,
) -> Any:
    """Open one local or GCS-backed Parquet file for Arrow."""
    if config.artifact_storage != "gcs":
        return Path(path).open("rb")
    return (filesystem or _gcs_filesystem(config)).open(path, "rb")


def _parquet_row_count(
    paths: Sequence[Path | str], config: StagedIngestionConfig
) -> int:
    """Read Parquet metadata only, avoiding a full in-memory row count."""
    total = 0
    filesystem = _gcs_filesystem(config) if config.artifact_storage == "gcs" else None
    for path in paths:
        with _parquet_file(path, config, filesystem=filesystem) as source:
            total += parquet.ParquetFile(source).metadata.num_rows
    return total


def _parquet_distinct_id_count(
    paths: Sequence[Path | str], config: StagedIngestionConfig
) -> tuple[int, int]:
    """Return ``(rows, distinct_ids)`` without holding all IDs in RAM.

    Archive sources use the canonical ``id`` as the Elasticsearch document ID.
    A source export can contain repeated IDs, which Elasticsearch correctly
    upserts rather than storing as multiple documents.  A disk-backed SQLite
    set keeps validation exact while remaining safe for multi-million-row
    exports and remote (GCS) Parquet files.
    """
    config.staging_dir.mkdir(parents=True, exist_ok=True)
    filesystem = _gcs_filesystem(config) if config.artifact_storage == "gcs" else None
    with tempfile.TemporaryDirectory(dir=config.staging_dir) as temporary_dir:
        database_path = Path(temporary_dir) / "distinct-ids.sqlite3"
        with sqlite3.connect(database_path) as database:
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            database.execute("CREATE TABLE ids (id TEXT PRIMARY KEY)")
            rows = 0
            for path in paths:
                with _parquet_file(path, config, filesystem=filesystem) as source:
                    parquet_file = parquet.ParquetFile(source)
                    for record_batch in parquet_file.iter_batches(
                        columns=["id"], batch_size=65_536
                    ):
                        values = record_batch.column(0).to_pylist()
                        rows += len(values)
                        database.executemany(
                            "INSERT OR IGNORE INTO ids (id) VALUES (?)",
                            ((str(value),) for value in values),
                        )
            distinct_ids = int(database.execute("SELECT COUNT(*) FROM ids").fetchone()[0])
    return rows, distinct_ids


def iter_parquet_models(
    paths: list[Path | str],
    model: type[ModelT],
    *,
    batch_size: int,
    config: StagedIngestionConfig,
) -> Iterator[ModelT]:
    """Read normalized Parquet files in bounded Arrow batches."""
    filesystem = _gcs_filesystem(config) if config.artifact_storage == "gcs" else None
    for path in paths:
        with _parquet_file(path, config, filesystem=filesystem) as source:
            for record_batch in parquet.ParquetFile(source).iter_batches(
                batch_size=batch_size
            ):
                for row in record_batch.to_pylist():
                    columns = list(row)
                    yield _model_from_row(columns, tuple(row.values()), model)


async def download_source(source: SourceName, config: StagedIngestionConfig) -> Path:
    """Ensure a source archive exists without copying GCS data onto pod disks."""
    read_timeout = 900.0 if source == "openfoodfacts" else 300.0
    timeout = httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)
    store = create_artifact_store(config)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        match source:
            case "usda-foundation":
                path = config.foundation_archive
                download: Callable[[], Any] = lambda: USDAFoundationClient(
                    client
                ).get_foundations(str(path))
            case "usda-branded":
                path = config.branded_archive
                download = lambda: USDAFoundationClient(client).get_branded(str(path))
            case "openfoodfacts":
                path = config.openfoodfacts_archive
                download = lambda: OpenFoodFactsClient(client).get_facts(
                    str(path), show_progress=config.show_progress
                )
            case _:
                raise ValueError(
                    "Wikidata is queried directly and has no archive download"
                )
        key = artifact_key(source, path)
        remote_exists = await store.exists(key)
        logger = structlog.get_logger(__name__)
        logger.info(
            "source_archive_preparation_started",
            source=source,
            local_exists=path.exists(),
            remote_exists=remote_exists,
            artifact_key=key,
        )
        if config.artifact_storage == "gcs":
            if config.force_download:
                raise ValueError(
                    "Force-download is disabled for GCS ingestion because it can "
                    "exhaust Kubernetes ephemeral storage; replace the GCS object "
                    "outside the ingestion pod instead"
                )
            if not remote_exists:
                raise FileNotFoundError(
                    f"GCS artifact {key!r} is not available; upload it to the "
                    "configured ingestion bucket before starting this flow"
                )
            logger.info(
                "source_archive_available_for_streaming",
                source=source,
                artifact_key=key,
            )
            return path
        if config.force_download:
            path.parent.mkdir(parents=True, exist_ok=True)
            await download()
            await store.upload(path, key)
            logger.info("source_archive_downloaded_and_uploaded", source=source)
        elif not path.exists() and remote_exists:
            await store.download(key, path)
            logger.info("source_archive_restored", source=source)
        elif not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            await download()
            await store.upload(path, key)
            logger.info("source_archive_downloaded_and_uploaded", source=source)
        elif not remote_exists:
            await store.upload(path, key)
            logger.info("source_archive_uploaded", source=source)
        logger.info(
            "source_archive_ready",
            source=source,
            path=str(path),
            size_mib=round(_file_size_megabytes(path), 1),
        )
        return path


async def materialize_source(source: SourceName, config: StagedIngestionConfig) -> Path:
    """Ensure an archive is available locally for a transform stage."""
    if source == "wikidata":
        raise ValueError("Wikidata has no archive to materialize")
    path = {
        "usda-foundation": config.foundation_archive,
        "usda-branded": config.branded_archive,
        "openfoodfacts": config.openfoodfacts_archive,
    }[source]
    store = create_artifact_store(config)
    logger = structlog.get_logger(__name__)
    if config.artifact_storage == "gcs":
        key = artifact_key(source, path)
        if not await store.exists(key):
            raise FileNotFoundError(f"GCS artifact {key!r} is not available")
        logger.info(
            "source_archive_streamed_from_gcs",
            source=source,
            artifact_key=key,
        )
        return path
    if not path.exists():
        logger.info(
            "source_archive_restore_started",
            source=source,
            artifact_key=artifact_key(source, path),
        )
        await store.download(artifact_key(source, path), path)
    logger.info(
        "source_archive_available",
        source=source,
        path=str(path),
        size_mib=round(_file_size_megabytes(path), 1),
    )
    return path


async def index_staged_source(
    source: SourceName,
    config: StagedIngestionConfig,
) -> int:
    """Stream durable Parquet batches into one Elasticsearch snapshot."""
    logger = structlog.get_logger(__name__)
    logger.info(
        "elasticsearch_index_started",
        source=source,
        batch_size=config.repository_batch_size,
    )
    if source == "wikidata":
        pipeline = create_pipeline(source, config)
        total_records = int(
            pipeline.dataset()(f"SELECT COUNT(*) FROM {TABLES[source]}").fetchscalar()
        )
        manifest = None
        paths: list[Path | str] = []
    else:
        manifest = _require_current_manifest(source, config)
        paths = _parquet_paths(source, config)
        if not paths:
            raise RuntimeError(f"No normalized Parquet files found for {source}")
        total_records = manifest.total_rows
    logger.info(
        "elasticsearch_index_plan",
        source=source,
        total_records=total_records,
        total_batches=(total_records + config.repository_batch_size - 1)
        // config.repository_batch_size,
    )
    async with AsyncElasticsearch(
        config.elasticsearch_url,
        request_timeout=120,
    ) as elasticsearch:
        if source == "wikidata":
            target_index = await prepare_snapshot_index(
                elasticsearch,
                alias=INDEX_ALIASES[source],
                staging_dir=config.staging_dir,
            )
            indexed = await index_records(
                iter_models(pipeline, TABLES[source], FoodEntity),
                WikidataFoodRepository(
                    elasticsearch,
                    index_name=target_index,
                ).save_records,
                batch_size=config.repository_batch_size,
                total_records=total_records,
            )
            logger.info("elasticsearch_index_completed", source=source, records=indexed)
            return indexed

        assert manifest is not None
        target_index = manifest.elasticsearch.candidate_index
        if target_index is None or not await elasticsearch.indices.exists(
            index=target_index
        ):
            target_index = await prepare_snapshot_index(
                elasticsearch,
                alias=INDEX_ALIASES[source],
                staging_dir=None,
            )
            manifest.elasticsearch = ElasticsearchCheckpoint(
                candidate_index=target_index
            )
            _write_manifest(manifest, config)

        completed_files = set(manifest.elasticsearch.completed_files)
        for file_number, path in enumerate(paths, start=1):
            path_string = str(path)
            if path_string in completed_files:
                continue
            file_rows = _parquet_row_count([path], config)
            match source:
                case "usda-foundation":
                    model = FoundationFoodAggregate
                    save = USDARepository(
                        elasticsearch,
                        foundation_index_name=target_index,
                    ).save_foundations
                case "usda-branded":
                    model = BrandedFoodAggregate
                    save = USDARepository(
                        elasticsearch,
                        branded_index_name=target_index,
                    ).save_branded
                case "openfoodfacts":
                    model = OpenFoodFactsAggregate
                    save = OpenFoodFactsRepository(
                        elasticsearch,
                        index_name=target_index,
                    ).save_records
                case _:
                    raise AssertionError(f"Unsupported archive source: {source}")
            indexed = await index_records(
                iter_parquet_models(
                    [path],
                    model,
                    batch_size=config.repository_batch_size,
                    config=config,
                ),
                save,  # type: ignore[arg-type]
                batch_size=config.repository_batch_size,
                total_records=file_rows,
            )
            if indexed != file_rows:
                raise RuntimeError(
                    f"Indexed {indexed} of {file_rows} records from {path_string}"
                )
            manifest.elasticsearch.completed_files.append(path_string)
            manifest.elasticsearch.indexed_records += indexed
            _write_manifest(manifest, config)
            logger.info(
                "elasticsearch_parquet_file_completed",
                source=source,
                file_number=file_number,
                total_files=len(paths),
                records=indexed,
                files_remaining=len(paths) - file_number,
            )
        logger.info(
            "elasticsearch_index_completed",
            source=source,
            records=manifest.elasticsearch.indexed_records,
        )
        return manifest.elasticsearch.indexed_records


async def validate_staged_source(
    source: SourceName,
    config: StagedIngestionConfig,
) -> tuple[int, int]:
    """Validate a candidate snapshot and publish it through stable aliases."""
    logger = structlog.get_logger(__name__)
    logger.info("elasticsearch_validation_started", source=source)
    if source == "wikidata":
        pipeline = create_pipeline(source, config)
        dataset = pipeline.dataset()
        staged_rows = int(
            dataset(f"SELECT COUNT(*) FROM {TABLES[source]}").fetchscalar()
        )
        staged = int(
            dataset(f"SELECT COUNT(DISTINCT id) FROM {TABLES[source]}").fetchscalar()
        )
        candidate_from_manifest = None
    else:
        manifest = _require_current_manifest(source, config)
        paths = _parquet_paths(source, config)
        staged_rows, staged = _parquet_distinct_id_count(paths, config)
        if staged_rows != manifest.total_rows:
            raise RuntimeError(
                f"{source} staging row mismatch: manifest={manifest.total_rows}, "
                f"parquet={staged_rows}"
            )
        candidate_from_manifest = manifest.elasticsearch.candidate_index
        if candidate_from_manifest is None:
            raise RuntimeError(f"No Elasticsearch candidate exists for {source}")
        if len(manifest.elasticsearch.completed_files) != len(
            _parquet_paths(source, config)
        ):
            raise RuntimeError(f"Elasticsearch indexing is incomplete for {source}")
    async with AsyncElasticsearch(config.elasticsearch_url) as elasticsearch:
        candidate = (
            candidate_from_manifest
            if candidate_from_manifest is not None
            else await pending_snapshot_index(
                elasticsearch,
                alias=INDEX_ALIASES[source],
                staging_dir=config.staging_dir,
            )
        )
        if not await elasticsearch.indices.exists(index=candidate):
            raise RuntimeError(f"Elasticsearch candidate does not exist: {candidate}")
        await elasticsearch.indices.refresh(index=candidate)
        indexed = int((await elasticsearch.count(index=candidate))["count"])
        if staged == indexed:
            await publish_snapshot_index(
                elasticsearch,
                alias=INDEX_ALIASES[source],
                candidate=candidate,
                staging_dir=config.staging_dir if source == "wikidata" else None,
            )
            if source != "wikidata":
                manifest.elasticsearch.published = True
                _write_manifest(manifest, config)
            logger.info(
                "elasticsearch_snapshot_published",
                source=source,
                index=candidate,
            )
    if staged != indexed:
        raise RuntimeError(
            f"{source} count mismatch: staging_unique={staged}, "
            f"staging_rows={staged_rows}, elasticsearch={indexed}"
        )
    logger.info(
        "elasticsearch_validation_completed",
        source=source,
        staging_rows=staged_rows,
        unique_ids=staged,
        duplicate_ids=staged_rows - staged,
        indexed=indexed,
    )
    return staged, indexed
