"""Durable, independently executable ingestion stages for Kestra."""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, get_args, get_origin

import dlt
import httpx
from elasticsearch import AsyncElasticsearch
from pydantic import BaseModel

from app.clients.openfoodfacts.client import OpenFoodFactsClient
from app.clients.openfoodfacts.reader import OpenFoodFactsReader
from app.clients.usda_fdc.client import USDAFoundationClient
from app.clients.usda_fdc.reader import USDAFoodDataReader
from app.aggregates import (
    BrandedFood as BrandedFoodAggregate,
    FoundationFood as FoundationFoodAggregate,
    OpenFoodFactsProduct as OpenFoodFactsAggregate,
)
from app.ingestion.elasticsearch_snapshots import (
    pending_snapshot_index,
    prepare_snapshot_index,
    publish_snapshot_index,
)
from app.ingestion.models import (
    FoodEntityRecord,
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
    repository_batch_size: int = 500
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
    """Create or attach to one source's persistent dlt pipeline."""
    config.pipelines_dir.mkdir(parents=True, exist_ok=True)
    config.staging_dir.mkdir(parents=True, exist_ok=True)
    pipeline_name = PIPELINE_NAMES[source]
    destination = dlt.destinations.duckdb(
        credentials=str(config.staging_dir / f"{pipeline_name}.duckdb")
    )
    return dlt.pipeline(
        pipeline_name=pipeline_name,
        pipelines_dir=str(config.pipelines_dir),
        destination=destination,
        # Keep the DuckDB catalog name and schema name distinct. DuckDB treats
        # identical catalog/schema identifiers as ambiguous in qualified SQL.
        dataset_name=f"{pipeline_name}_data",
    )


@dlt.resource(
    name="usda_foundation_documents",
    primary_key="id",
    write_disposition="replace",
    columns=FoundationFoodAggregate,
)
def usda_foundation_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Foundation Foods into canonical documents."""
    for food in USDAFoodDataReader().iter_foundation_foods(path):
        yield food.to_domain().model_dump(mode="json")


@dlt.resource(
    name="usda_branded_documents",
    primary_key="id",
    write_disposition="replace",
    columns=BrandedFoodAggregate,
)
def usda_branded_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Branded Foods into canonical documents."""
    for food in USDAFoodDataReader().iter_branded_foods(path):
        yield food.to_domain().model_dump(mode="json")


@dlt.resource(
    name="openfoodfacts_documents",
    primary_key="id",
    write_disposition="replace",
    columns=OpenFoodFactsAggregate,
)
def openfoodfacts_documents_resource(path: Path) -> Iterator[dict[str, Any]]:
    """Validate and transform Open Food Facts products into canonical documents."""
    for product in OpenFoodFactsReader().iter_products(path):
        yield product.to_domain().model_dump(mode="json")


def extract_source_documents(source: SourceName, config: StagedIngestionConfig) -> Any:
    """Extract and transform an archive into a pending dlt load package."""
    pipeline = create_pipeline(source, config)
    match source:
        case "usda-foundation":
            resource = usda_foundation_documents_resource(config.foundation_archive)
        case "usda-branded":
            resource = usda_branded_documents_resource(config.branded_archive)
        case "openfoodfacts":
            resource = openfoodfacts_documents_resource(config.openfoodfacts_archive)
        case _:
            raise ValueError("Wikidata uses its base/detail extraction stages")
    return pipeline.extract(resource)


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
    return create_pipeline(source, config).normalize()


def load_pending(source: SourceName, config: StagedIngestionConfig) -> Any:
    """Load all normalized packages into one source's DuckDB staging database."""
    return create_pipeline(source, config).load()


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


async def download_source(source: SourceName, config: StagedIngestionConfig) -> Path:
    """Download an archive when absent, preserving it for subsequent stages."""
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
        if config.force_download or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            await download()
            await store.upload(path, key)
        elif not remote_exists:
            await store.upload(path, key)
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
    if not path.exists():
        await store.download(artifact_key(source, path), path)
    return path


async def index_staged_source(
    source: SourceName,
    config: StagedIngestionConfig,
) -> int:
    """Stream one normalized dlt table into its Elasticsearch repository."""
    pipeline = create_pipeline(source, config)
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
                records = iter_models(pipeline, TABLES[source], FoodEntityRecord)
                save = WikidataFoodRepository(
                    elasticsearch,
                    index_name=target_index,
                ).save_records
            case "usda-foundation":
                records = iter_models(
                    pipeline,
                    TABLES[source],
                    FoundationFoodAggregate,
                )
                save = USDARepository(
                    elasticsearch,
                    foundation_index_name=target_index,
                ).save_foundations
            case "usda-branded":
                records = iter_models(
                    pipeline,
                    TABLES[source],
                    BrandedFoodAggregate,
                )
                save = USDARepository(
                    elasticsearch,
                    branded_index_name=target_index,
                ).save_branded
            case "openfoodfacts":
                records = iter_models(
                    pipeline,
                    TABLES[source],
                    OpenFoodFactsAggregate,
                )
                save = OpenFoodFactsRepository(
                    elasticsearch,
                    index_name=target_index,
                ).save_records
        return await index_records(
            records,
            save,
            batch_size=config.repository_batch_size,
        )


async def validate_staged_source(
    source: SourceName,
    config: StagedIngestionConfig,
) -> tuple[int, int]:
    """Validate a candidate snapshot and publish it through stable aliases."""
    pipeline = create_pipeline(source, config)
    dataset = pipeline.dataset()
    # Elasticsearch stores one document per primary key.  A source may contain
    # repeated rows for the same entity (Open Food Facts currently has such
    # duplicates), and indexing those rows replaces the previous document.
    # Validate against the number of unique IDs rather than the raw row count.
    staged_rows = int(
        dataset(f"SELECT COUNT(*) FROM {TABLES[source]}").fetchscalar()
    )
    staged = int(
        dataset(
            f"SELECT COUNT(DISTINCT id) FROM {TABLES[source]}"
        ).fetchscalar()
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
    if staged != indexed:
        raise RuntimeError(
            f"{source} count mismatch: staging_unique={staged}, "
            f"staging_rows={staged_rows}, elasticsearch={indexed}"
        )
    return staged, indexed
