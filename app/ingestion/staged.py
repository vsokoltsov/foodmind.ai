"""Durable, independently executable ingestion stages for Kestra."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, get_args, get_origin

import dlt
import gcsfs
import httpx
import structlog
from elasticsearch import AsyncElasticsearch
from pydantic import BaseModel
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
    source_batch_size: int = 2_000
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


def create_pipeline(source: SourceName, config: StagedIngestionConfig) -> Any:
    """Create one dlt pipeline with a durable Parquet destination.

    The filesystem destination writes Parquet directly to GCS through
    ``gcsfs``. A completed ``pipeline.run`` therefore leaves a durable load
    package behind even when the Kubernetes task pod is interrupted. The dlt
    working state stays on the durable task-data PVC, avoiding a dependency on
    the GCS FUSE CSI add-on.
    """
    config.pipelines_dir.mkdir(parents=True, exist_ok=True)
    config.staging_dir.mkdir(parents=True, exist_ok=True)
    config.normalized_dir.mkdir(parents=True, exist_ok=True)
    pipeline_name = PIPELINE_NAMES[source]
    if source != "wikidata" and config.artifact_storage == "gcs":
        if not config.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for GCS-backed dlt ingestion")
        destination = dlt.destinations.filesystem(
            bucket_url=(
                f"gs://{config.gcs_bucket}/"
                f"{config.gcs_prefix.strip('/')}/dlt-normalized"
            )
        )
    elif source != "wikidata":
        destination = dlt.destinations.filesystem(bucket_url=str(config.normalized_dir))
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

    Kestra retries can occur after a worker interruption. The dlt working
    directory is on the durable task-data volume, so ``flock`` rejects a
    duplicate process before it can mutate the same pipeline state.
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


def openfoodfacts_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Open Food Facts products into canonical documents."""
    for product in OpenFoodFactsReader().iter_products(path):
        yield product.to_domain().model_dump(mode="json")


ARCHIVE_MODELS: dict[SourceName, type[BaseModel]] = {
    "usda-foundation": FoundationFoodAggregate,
    "usda-branded": BrandedFoodAggregate,
    "openfoodfacts": OpenFoodFactsAggregate,
}


def _archive_documents(source: SourceName, config: StagedIngestionConfig) -> Iterator[dict[str, Any]]:
    """Yield canonical documents for one archive-backed source."""
    match source:
        case "usda-foundation":
            yield from usda_foundation_documents_resource(config.foundation_archive)
        case "usda-branded":
            yield from usda_branded_documents_resource(config.branded_archive)
        case "openfoodfacts":
            yield from openfoodfacts_documents_resource(config.openfoodfacts_archive)
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

    Each call to ``pipeline.run`` commits one source batch.  At startup dlt
    first finishes any package left pending by an interrupted pod; completed
    package count then identifies the already committed leading batches.  A
    retry may scan the compressed input to that point, but it never rebuilds
    or reloads the completed normalized data.
    """
    if source == "wikidata":
        raise ValueError("Wikidata uses its dedicated staged flow")
    with source_pipeline_lock(source, config):
        logger = structlog.get_logger(__name__)
        pipeline = create_pipeline(source, config)
        _discard_incompatible_legacy_pending_packages(source, config, pipeline)
        pipeline.load()
        completed_batches = len(pipeline.list_completed_load_packages())
        logger.info(
            "dlt_parquet_batch_processing_started",
            source=source,
            source_batch_size=config.source_batch_size,
            completed_batches=completed_batches,
        )
        processed_records = 0
        for batch_number, documents in enumerate(
            _document_batches(_archive_documents(source, config), config.source_batch_size),
            start=1,
        ):
            if batch_number <= completed_batches:
                continue
            pipeline.run(_batch_resource(source, documents))
            processed_records += len(documents)
            logger.info(
                "dlt_parquet_batch_completed",
                source=source,
                batch_number=batch_number,
                records_in_batch=len(documents),
                records_processed=processed_records,
                batches_remaining=None,
            )
        logger.info(
            "dlt_parquet_batch_processing_completed",
            source=source,
            newly_processed_records=processed_records,
            completed_batches=len(pipeline.list_completed_load_packages()),
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


def _parquet_paths(source: SourceName, config: StagedIngestionConfig) -> list[Path | str]:
    """Return the durable Parquet files written for an archive source."""
    pipeline_name = PIPELINE_NAMES[source]
    if config.artifact_storage == "gcs":
        if not config.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for GCS-backed dlt ingestion")
        prefix = "/".join(
            (
                config.gcs_prefix.strip("/"),
                "dlt-normalized",
                f"{pipeline_name}_data",
                TABLES[source],
                "*.parquet",
            )
        )
        filesystem = gcsfs.GCSFileSystem(project=config.gcp_project_id)
        return sorted(filesystem.glob(f"{config.gcs_bucket}/{prefix}"))
    table_dir = config.normalized_dir / f"{pipeline_name}_data" / TABLES[source]
    return sorted(table_dir.glob("*.parquet")) if table_dir.exists() else []


def _parquet_file(path: Path | str, config: StagedIngestionConfig) -> Any:
    """Open one local or GCS-backed Parquet file for Arrow."""
    if isinstance(path, Path):
        return path.open("rb")
    return gcsfs.GCSFileSystem(project=config.gcp_project_id).open(path, "rb")


def _parquet_row_count(paths: list[Path | str], config: StagedIngestionConfig) -> int:
    """Read Parquet metadata only, avoiding a full in-memory row count."""
    total = 0
    for path in paths:
        with _parquet_file(path, config) as source:
            total += parquet.ParquetFile(source).metadata.num_rows
    return total


def iter_parquet_models(
    paths: list[Path | str],
    model: type[ModelT],
    *,
    batch_size: int,
    config: StagedIngestionConfig,
) -> Iterator[ModelT]:
    """Read normalized Parquet files in bounded Arrow batches."""
    for path in paths:
        with _parquet_file(path, config) as source:
            for record_batch in parquet.ParquetFile(source).iter_batches(
                batch_size=batch_size
            ):
                for row in record_batch.to_pylist():
                    columns = list(row)
                    yield _model_from_row(columns, tuple(row.values()), model)


async def download_source(source: SourceName, config: StagedIngestionConfig) -> Path:
    """Ensure a source archive exists locally and in artifact storage.

    A restarted Kestra pod has no local source cache. When a prior download is
    already in the configured artifact store, restore that object instead of
    downloading the public export again.
    """
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
                download = lambda: USDAFoundationClient(client).get_branded(
                    str(path)
                )
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
    pipeline = create_pipeline(source, config)
    logger = structlog.get_logger(__name__)
    logger.info(
        "elasticsearch_index_started",
        source=source,
        batch_size=config.repository_batch_size,
    )
    if source == "wikidata":
        total_records = int(
            pipeline.dataset()(f"SELECT COUNT(*) FROM {TABLES[source]}").fetchscalar()
        )
    else:
        paths = _parquet_paths(source, config)
        if not paths:
            raise RuntimeError(f"No normalized Parquet files found for {source}")
        total_records = _parquet_row_count(paths, config)
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
        target_index = await prepare_snapshot_index(
            elasticsearch,
            alias=INDEX_ALIASES[source],
            staging_dir=config.staging_dir,
        )
        match source:
            case "wikidata":
                records = iter_models(pipeline, TABLES[source], FoodEntity)
                save = WikidataFoodRepository(
                    elasticsearch,
                    index_name=target_index,
                ).save_records
            case "usda-foundation":
                records = iter_parquet_models(
                    paths,
                    FoundationFoodAggregate,
                    batch_size=config.repository_batch_size,
                    config=config,
                )
                save = USDARepository(
                    elasticsearch,
                    foundation_index_name=target_index,
                ).save_foundations
            case "usda-branded":
                records = iter_parquet_models(
                    paths,
                    BrandedFoodAggregate,
                    batch_size=config.repository_batch_size,
                    config=config,
                )
                save = USDARepository(
                    elasticsearch,
                    branded_index_name=target_index,
                ).save_branded
            case "openfoodfacts":
                records = iter_parquet_models(
                    paths,
                    OpenFoodFactsAggregate,
                    batch_size=config.repository_batch_size,
                    config=config,
                )
                save = OpenFoodFactsRepository(
                    elasticsearch,
                    index_name=target_index,
                ).save_records
        indexed = await index_records(
            records,
            save,  # type: ignore[arg-type]
            batch_size=config.repository_batch_size,
            total_records=total_records,
        )
        logger.info("elasticsearch_index_completed", source=source, records=indexed)
        return indexed


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
            dataset(
                f"SELECT COUNT(DISTINCT id) FROM {TABLES[source]}"
            ).fetchscalar()
        )
    else:
        paths = _parquet_paths(source, config)
        staged_rows = _parquet_row_count(paths, config)
        # Elasticsearch has one document per primary key. Keeping only the
        # identifiers here is bounded by the source cardinality rather than
        # the much larger source payload, and validation runs independently
        # from the memory-sensitive normalization work.
        staged = len(
            {
                str(record.model_dump()["id"])
                for record in iter_parquet_models(
                    paths,
                    ARCHIVE_MODELS[source],
                    batch_size=config.repository_batch_size,
                    config=config,
                )
            }
        )
    async with AsyncElasticsearch(config.elasticsearch_url) as elasticsearch:
        candidate = await pending_snapshot_index(
            elasticsearch,
            alias=INDEX_ALIASES[source],
            staging_dir=config.staging_dir,
        )
        await elasticsearch.indices.refresh(index=candidate)
        indexed = int((await elasticsearch.count(index=candidate))["count"])
        if staged == indexed:
            await publish_snapshot_index(
                elasticsearch,
                alias=INDEX_ALIASES[source],
                candidate=candidate,
                staging_dir=config.staging_dir,
            )
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
        indexed=indexed,
    )
    return staged, indexed
