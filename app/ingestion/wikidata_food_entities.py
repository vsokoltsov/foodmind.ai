"""Two-stage dlt ingestion pipeline for normalized Wikidata food entities."""

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar, get_args, get_origin

import dlt
import httpx
from pydantic import BaseModel

from app.clients.wikidata_food_entities.client import WikidataFoodEntitiesClient
from app.ingestion.models import (
    FoodEntityRecord,
    RelatedEntity,
    WikidataAliasRecord,
    WikidataEntityRecord,
    WikidataMediaArticleRecord,
    WikidataOriginRecord,
    WikidataTaxonomyRecord,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
JSON_CONTAINER_TYPES = (list, dict, tuple, set, frozenset)


@dataclass(frozen=True)
class WikidataIngestionLoadInfo:
    """Load information for each stage of the Wikidata pipeline."""

    entities: Any
    details: Any | None
    normalized: Any


@asynccontextmanager
async def _client_scope(
    client: WikidataFoodEntitiesClient | None,
    *,
    batch_size: int = 100,
) -> AsyncIterator[WikidataFoodEntitiesClient]:
    """Yield an injected client or create and close a resource-local client."""
    if client is not None:
        yield client
        return

    timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as http_client:
        # Each detail resource performs its batches sequentially. dlt runs the four
        # async resources concurrently, keeping total endpoint concurrency bounded.
        yield WikidataFoodEntitiesClient(
            client=http_client,
            batch_size=batch_size,
            concurrency=1,
        )


@dlt.resource(
    name="wikidata_entities",
    primary_key="id",
    write_disposition="replace",
    columns=WikidataEntityRecord,
)
async def wikidata_entities_resource(
    *,
    client: WikidataFoodEntitiesClient | None = None,
) -> Any:
    """Yield the base Wikidata food entities used by later stages."""
    async with _client_scope(client) as wikidata_client:
        response = await wikidata_client.get_entities()
        yield [
            WikidataEntityRecord(
                id=binding.item.qid_from_uri,
                label=binding.item_label.value,
                description=(
                    binding.item_description.value
                    if binding.item_description is not None
                    else None
                ),
            ).model_dump(mode="json")
            for binding in response.results.bindings
        ]


@dlt.resource(
    name="wikidata_aliases",
    write_disposition="replace",
    columns=WikidataAliasRecord,
)
async def wikidata_aliases_resource(
    qids: list[str],
    *,
    batch_size: int = 100,
    show_progress: bool = False,
    client: WikidataFoodEntitiesClient | None = None,
) -> Any:
    """Yield alias rows for the supplied Wikidata entity IDs."""
    async with _client_scope(client, batch_size=batch_size) as wikidata_client:
        response = await wikidata_client.get_aliases(
            qids,
            show_progress=show_progress,
        )
        yield [
            WikidataAliasRecord(
                item_id=binding.item.qid_from_uri,
                alias=binding.alias.value,
            ).model_dump(mode="json")
            for binding in response.results.bindings
        ]


@dlt.resource(
    name="wikidata_taxonomy",
    write_disposition="replace",
    columns=WikidataTaxonomyRecord,
)
async def wikidata_taxonomy_resource(
    qids: list[str],
    *,
    batch_size: int = 100,
    show_progress: bool = False,
    client: WikidataFoodEntitiesClient | None = None,
) -> Any:
    """Yield taxonomy rows for the supplied Wikidata entity IDs."""
    async with _client_scope(client, batch_size=batch_size) as wikidata_client:
        response = await wikidata_client.get_taxonomy(
            qids,
            show_progress=show_progress,
        )
        yield [
            WikidataTaxonomyRecord(
                item_id=binding.item.qid_from_uri,
                instance_id=(
                    binding.instance.qid_from_uri
                    if binding.instance is not None
                    else None
                ),
                instance_label=(
                    binding.instance_label.value
                    if binding.instance_label is not None
                    else None
                ),
                subclass_id=(
                    binding.subclass.qid_from_uri
                    if binding.subclass is not None
                    else None
                ),
                subclass_label=(
                    binding.subclass_label.value
                    if binding.subclass_label is not None
                    else None
                ),
            ).model_dump(mode="json")
            for binding in response.results.bindings
        ]


@dlt.resource(
    name="wikidata_origins",
    write_disposition="replace",
    columns=WikidataOriginRecord,
)
async def wikidata_origins_resource(
    qids: list[str],
    *,
    batch_size: int = 100,
    show_progress: bool = False,
    client: WikidataFoodEntitiesClient | None = None,
) -> Any:
    """Yield country-of-origin and cuisine rows for Wikidata entity IDs."""
    async with _client_scope(client, batch_size=batch_size) as wikidata_client:
        response = await wikidata_client.get_original_cousine(
            qids,
            show_progress=show_progress,
        )
        yield [
            WikidataOriginRecord(
                item_id=binding.item.qid_from_uri,
                country_id=(
                    binding.country.qid_from_uri
                    if binding.country is not None
                    else None
                ),
                country_label=(
                    binding.country_label.value
                    if binding.country_label is not None
                    else None
                ),
                cuisine_id=(
                    binding.cuisine.qid_from_uri
                    if binding.cuisine is not None
                    else None
                ),
                cuisine_label=(
                    binding.cuisine_label.value
                    if binding.cuisine_label is not None
                    else None
                ),
            ).model_dump(mode="json")
            for binding in response.results.bindings
        ]


@dlt.resource(
    name="wikidata_media_articles",
    write_disposition="replace",
    columns=WikidataMediaArticleRecord,
)
async def wikidata_media_articles_resource(
    qids: list[str],
    *,
    batch_size: int = 100,
    show_progress: bool = False,
    client: WikidataFoodEntitiesClient | None = None,
) -> Any:
    """Yield image and Wikipedia article rows for Wikidata entity IDs."""
    async with _client_scope(client, batch_size=batch_size) as wikidata_client:
        response = await wikidata_client.get_media_articles(
            qids,
            show_progress=show_progress,
        )
        yield [
            WikidataMediaArticleRecord(
                item_id=binding.item.qid_from_uri,
                image=binding.image.value if binding.image is not None else None,
                article=binding.article.value if binding.article is not None else None,
            ).model_dump(mode="json")
            for binding in response.results.bindings
        ]


@dlt.source(name="wikidata_food_entity_details")
def wikidata_details_source(
    qids: list[str],
    *,
    batch_size: int = 100,
    show_progress: bool = False,
    client: WikidataFoodEntitiesClient | None = None,
) -> Sequence[Any]:
    """Create four independent async resources for Wikidata detail queries."""
    resource_arguments = {
        "batch_size": batch_size,
        "show_progress": show_progress,
        "client": client,
    }
    return (
        wikidata_aliases_resource(qids, **resource_arguments),
        wikidata_taxonomy_resource(qids, **resource_arguments),
        wikidata_origins_resource(qids, **resource_arguments),
        wikidata_media_articles_resource(qids, **resource_arguments),
    )


def _append_unique[T](values: list[T], value: T) -> None:
    """Append a value only when it is not already present."""
    if value not in values:
        values.append(value)


def normalize_food_entity_records(
    entities: Sequence[WikidataEntityRecord],
    aliases: Sequence[WikidataAliasRecord],
    taxonomy: Sequence[WikidataTaxonomyRecord],
    origins: Sequence[WikidataOriginRecord],
    media_articles: Sequence[WikidataMediaArticleRecord],
) -> list[FoodEntityRecord]:
    """Join staged Wikidata rows into one normalized record per entity."""
    records = {
        entity.id: FoodEntityRecord(
            id=entity.id,
            label=entity.label,
            description=entity.description,
        )
        for entity in entities
    }

    for alias in aliases:
        if record := records.get(alias.item_id):
            _append_unique(record.aliases, alias.alias)

    for row in taxonomy:
        record = records.get(row.item_id)
        if record is None:
            continue
        if row.instance_id is not None:
            _append_unique(
                record.instance_of,
                RelatedEntity(id=row.instance_id, label=row.instance_label),
            )
        if row.subclass_id is not None:
            _append_unique(
                record.subclasses,
                RelatedEntity(id=row.subclass_id, label=row.subclass_label),
            )

    for row in origins:
        record = records.get(row.item_id)
        if record is None:
            continue
        if row.country_id is not None:
            _append_unique(
                record.countries,
                RelatedEntity(id=row.country_id, label=row.country_label),
            )
        if row.cuisine_id is not None:
            _append_unique(
                record.cuisines,
                RelatedEntity(id=row.cuisine_id, label=row.cuisine_label),
            )

    for row in media_articles:
        record = records.get(row.item_id)
        if record is None:
            continue
        if row.image is not None:
            _append_unique(record.images, row.image)
        if row.article is not None:
            _append_unique(record.articles, row.article)

    return list(records.values())


def _read_models(
    pipeline: Any,
    table_name: str,
    model: type[ModelT],
) -> list[ModelT]:
    """Read a staged dlt table into Pydantic models."""
    columns = list(model.model_fields)
    rows = pipeline.dataset().table(table_name).select(*columns).fetchall()
    records = []
    for row in rows:
        values = dict(zip(columns, row))
        # dlt maps nested Pydantic fields to DuckDB's JSON type. DuckDB returns
        # those values as JSON text, so restore them before Pydantic validation.
        for column, value in values.items():
            if (
                isinstance(value, str)
                and value.startswith(("[", "{"))
                and _expects_json_value(model.model_fields[column].annotation)
            ):
                values[column] = json.loads(value)
        records.append(model.model_validate(values))
    return records


def _expects_json_value(annotation: Any) -> bool:
    """Return whether a model annotation represents JSON-backed structured data."""
    origin = get_origin(annotation)
    if annotation in JSON_CONTAINER_TYPES or origin in JSON_CONTAINER_TYPES:
        return True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return any(_expects_json_value(argument) for argument in get_args(annotation))


@dlt.resource(
    name="food_entities",
    primary_key="id",
    write_disposition="replace",
    columns=FoodEntityRecord,
)
def normalized_food_entities_resource(
    records: Sequence[FoodEntityRecord],
) -> Any:
    """Yield final normalized records after all staged tables are loaded."""
    yield [record.model_dump(mode="json") for record in records]


def run_pipeline_stages(
    pipeline: Any,
    *,
    batch_size: int = 100,
    show_progress: bool = False,
    client: WikidataFoodEntitiesClient | None = None,
) -> WikidataIngestionLoadInfo:
    """Run base extraction, parallel details, and normalization in order."""

    # 1. Retrieve main information (ids, basically)
    entities_load = pipeline.run(wikidata_entities_resource(client=client))
    entities = _read_models(pipeline, "wikidata_entities", WikidataEntityRecord)
    qids = [f"wd:{entity.id}" for entity in entities]

    # 2. Fetch detailed information concurrently
    details_load = None
    if qids:
        details_load = pipeline.run(
            wikidata_details_source(
                qids,
                batch_size=batch_size,
                show_progress=show_progress,
                client=client,
            )
        )

    aliases = _read_models(pipeline, "wikidata_aliases", WikidataAliasRecord) if qids else []
    taxonomy = (
        _read_models(pipeline, "wikidata_taxonomy", WikidataTaxonomyRecord)
        if qids
        else []
    )
    origins = _read_models(pipeline, "wikidata_origins", WikidataOriginRecord) if qids else []
    media_articles = (
        _read_models(
            pipeline,
            "wikidata_media_articles",
            WikidataMediaArticleRecord,
        )
        if qids
        else []
    )
    normalized_records = normalize_food_entity_records(
        entities,
        aliases,
        taxonomy,
        origins,
        media_articles,
    )
    normalized_load = pipeline.run(
        normalized_food_entities_resource(normalized_records)
    )
    return WikidataIngestionLoadInfo(
        entities=entities_load,
        details=details_load,
        normalized=normalized_load,
    )


def run_pipeline(
    *,
    pipeline_name: str = "wikidata_food_entities",
    destination: str = "duckdb",
    dataset_name: str = "foodmind",
    batch_size: int = 100,
    show_progress: bool = False,
) -> WikidataIngestionLoadInfo:
    """Create and run the two-stage Wikidata food entity pipeline."""
    load_info, _records = run_pipeline_with_records(
        pipeline_name=pipeline_name,
        destination=destination,
        dataset_name=dataset_name,
        batch_size=batch_size,
        show_progress=show_progress,
    )
    return load_info


def run_pipeline_with_records(
    *,
    pipeline_name: str = "wikidata_food_entities",
    destination: str = "duckdb",
    dataset_name: str = "foodmind",
    batch_size: int = 100,
    show_progress: bool = False,
) -> tuple[WikidataIngestionLoadInfo, list[FoodEntityRecord]]:
    """Run the dlt stages and return normalized records for a final sink."""
    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=destination,
        dataset_name=dataset_name,
    )
    load_info = run_pipeline_stages(
        pipeline,
        batch_size=batch_size,
        show_progress=show_progress,
    )
    records = _read_models(pipeline, "food_entities", FoodEntityRecord)
    return load_info, records
