"""Concurrent ingestion of all MVP sources into Elasticsearch."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import islice
from pathlib import Path
from typing import Any, TypeVar

import httpx
from elasticsearch import AsyncElasticsearch
from pydantic import BaseModel

from app.clients.openfoodfacts.client import OpenFoodFactsClient
from app.clients.openfoodfacts.reader import OpenFoodFactsReader
from app.clients.usda_fdc.client import USDAFoundationClient
from app.clients.usda_fdc.reader import USDAFoodDataReader
from app.ingestion.models import FoodEntityRecord
from app.ingestion.wikidata_food_entities import run_pipeline_with_records
from app.repositories.openfoodfacts import OpenFoodFactsRepository
from app.repositories.usda import USDARepository
from app.repositories.wikidata import WikidataFoodRepository

RecordT = TypeVar("RecordT", bound=BaseModel)
SaveBatch = Callable[[list[RecordT]], Awaitable[None]]
SourceJob = Callable[[], Awaitable["SourceIngestionResult"]]
WikidataLoader = Callable[..., tuple[Any, list[FoodEntityRecord]]]


@dataclass(frozen=True)
class IngestionConfig:
    """Runtime configuration for the multi-source ingestion pipeline."""

    elasticsearch_url: str = "http://localhost:9200"
    foundation_archive: Path = Path("foundations.json.zip")
    branded_archive: Path = Path("branded.json.zip")
    openfoodfacts_archive: Path = Path("openfoodfacts-products.jsonl.gz")
    repository_batch_size: int = 500
    wikidata_batch_size: int = 100
    wikidata_pipeline_name: str = "wikidata_food_entities"
    wikidata_destination: str = "duckdb"
    wikidata_dataset_name: str = "foodmind"
    show_progress: bool = False
    force_download: bool = False

    def __post_init__(self) -> None:
        """Validate positive batch sizes before any source starts."""
        if self.repository_batch_size < 1:
            raise ValueError("repository_batch_size must be at least 1")
        if self.wikidata_batch_size < 1:
            raise ValueError("wikidata_batch_size must be at least 1")


@dataclass(frozen=True)
class SourceIngestionResult:
    """Number of records indexed for one independently running source."""

    source: str
    records_indexed: int


@dataclass(frozen=True)
class IngestionResult:
    """Results from every source in deterministic source order."""

    sources: tuple[SourceIngestionResult, ...]

    @property
    def total_records_indexed(self) -> int:
        """Return the sum of records written by all source jobs."""
        return sum(source.records_indexed for source in self.sources)


def _take_batch(
    records: Iterator[RecordT],
    batch_size: int,
) -> list[RecordT]:
    """Read at most one batch from a synchronous streaming iterator."""
    return list(islice(records, batch_size))


async def index_records(
    records: Iterator[RecordT],
    save_batch: SaveBatch[RecordT],
    *,
    batch_size: int,
) -> int:
    """Parse a synchronous stream off-loop and index it in bounded batches."""
    indexed = 0
    iterator = iter(records)

    while True:
        batch = await asyncio.to_thread(_take_batch, iterator, batch_size)
        if not batch:
            return indexed

        await save_batch(batch)
        indexed += len(batch)


async def ingest_wikidata(
    repository: WikidataFoodRepository,
    config: IngestionConfig,
    *,
    loader: WikidataLoader = run_pipeline_with_records,
) -> SourceIngestionResult:
    """Run Wikidata's dlt stages and write normalized records to Elasticsearch."""
    load = partial(
        loader,
        pipeline_name=config.wikidata_pipeline_name,
        destination=config.wikidata_destination,
        dataset_name=config.wikidata_dataset_name,
        batch_size=config.wikidata_batch_size,
        show_progress=config.show_progress,
    )
    _load_info, records = await asyncio.to_thread(load)
    count = await index_records(
        iter(records),
        repository.save_records,
        batch_size=config.repository_batch_size,
    )
    return SourceIngestionResult(source="wikidata", records_indexed=count)


async def _download_if_needed(
    destination: Path,
    download: Callable[[], Awaitable[Any]],
    *,
    force: bool,
) -> None:
    """Download a source archive only when it is absent or explicitly forced."""
    if force or not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        await download()


async def ingest_usda_foundations(
    client: USDAFoundationClient,
    reader: USDAFoodDataReader,
    repository: USDARepository,
    config: IngestionConfig,
) -> SourceIngestionResult:
    """Download, stream, and index USDA Foundation Foods."""
    await _download_if_needed(
        config.foundation_archive,
        partial(client.get_foundations, str(config.foundation_archive)),
        force=config.force_download,
    )
    count = await index_records(
        reader.iter_foundation_foods(config.foundation_archive),
        repository.save_foundations,
        batch_size=config.repository_batch_size,
    )
    return SourceIngestionResult(source="usda_foundation", records_indexed=count)


async def ingest_usda_branded(
    client: USDAFoundationClient,
    reader: USDAFoodDataReader,
    repository: USDARepository,
    config: IngestionConfig,
) -> SourceIngestionResult:
    """Download, stream, and index USDA Branded Foods."""
    await _download_if_needed(
        config.branded_archive,
        partial(client.get_branded, str(config.branded_archive)),
        force=config.force_download,
    )
    count = await index_records(
        reader.iter_branded_foods(config.branded_archive),
        repository.save_branded,
        batch_size=config.repository_batch_size,
    )
    return SourceIngestionResult(source="usda_branded", records_indexed=count)


async def ingest_openfoodfacts(
    client: OpenFoodFactsClient,
    reader: OpenFoodFactsReader,
    repository: OpenFoodFactsRepository,
    config: IngestionConfig,
) -> SourceIngestionResult:
    """Download, stream, and index Open Food Facts products."""
    await _download_if_needed(
        config.openfoodfacts_archive,
        partial(
            client.get_facts,
            str(config.openfoodfacts_archive),
            show_progress=config.show_progress,
        ),
        force=config.force_download,
    )
    count = await index_records(
        reader.iter_products(config.openfoodfacts_archive),
        repository.save_records,
        batch_size=config.repository_batch_size,
    )
    return SourceIngestionResult(source="openfoodfacts", records_indexed=count)


async def run_sources_in_parallel(
    jobs: Sequence[SourceJob],
) -> IngestionResult:
    """Start all supplied source jobs concurrently and collect their results."""
    results = await asyncio.gather(*(job() for job in jobs))
    return IngestionResult(sources=tuple(results))


async def run_ingestion(
    config: IngestionConfig,
    *,
    wikidata_loader: WikidataLoader = run_pipeline_with_records,
) -> IngestionResult:
    """Run all MVP source ingestions concurrently into Elasticsearch."""
    timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
    async with (
        httpx.AsyncClient(follow_redirects=True, timeout=timeout) as http_client,
        AsyncElasticsearch(
            config.elasticsearch_url,
            request_timeout=120,
        ) as elasticsearch,
    ):
        usda_client = USDAFoundationClient(client=http_client)
        openfoodfacts_client = OpenFoodFactsClient(client=http_client)
        usda_reader = USDAFoodDataReader()

        usda_repository = USDARepository(elasticsearch)

        return await run_sources_in_parallel(
            (
                partial(
                    ingest_wikidata,
                    WikidataFoodRepository(elasticsearch),
                    config,
                    loader=wikidata_loader,
                ),
                partial(
                    ingest_usda_foundations,
                    usda_client,
                    usda_reader,
                    usda_repository,
                    config,
                ),
                partial(
                    ingest_usda_branded,
                    usda_client,
                    usda_reader,
                    usda_repository,
                    config,
                ),
                partial(
                    ingest_openfoodfacts,
                    openfoodfacts_client,
                    OpenFoodFactsReader(),
                    OpenFoodFactsRepository(elasticsearch),
                    config,
                ),
            )
        )
