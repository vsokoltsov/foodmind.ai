import asyncio
import threading
from pathlib import Path

import pytest

from app.ingestion.models import FoodEntityRecord
from app.ingestion.pipeline import (
    IngestionConfig,
    SourceIngestionResult,
    index_records,
    ingest_wikidata,
    run_sources_in_parallel,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_batch_size", 0),
        ("wikidata_batch_size", 0),
    ],
)
def test_rejects_non_positive_batch_sizes(field: str, value: int) -> None:
    with pytest.raises(ValueError, match=f"{field} must be at least 1"):
        IngestionConfig(**{field: value})


def test_indexes_stream_in_bounded_batches() -> None:
    records = iter(
        [FoodEntityRecord(id=f"Q{index}", label=f"Food {index}") for index in range(5)]
    )
    batches: list[list[str]] = []

    async def save(batch: list[FoodEntityRecord]) -> None:
        batches.append([record.id for record in batch])

    count = asyncio.run(index_records(records, save, batch_size=2))

    assert count == 5
    assert batches == [["Q0", "Q1"], ["Q2", "Q3"], ["Q4"]]


def test_runs_every_source_job_concurrently() -> None:
    state = {"active": 0, "maximum": 0, "started": 0}
    all_started = asyncio.Event()

    def job(source: str):
        async def run() -> SourceIngestionResult:
            state["active"] += 1
            state["started"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            if state["started"] == 4:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1)
            state["active"] -= 1
            return SourceIngestionResult(source=source, records_indexed=1)

        return run

    result = asyncio.run(
        run_sources_in_parallel(
            tuple(job(source) for source in ("wikidata", "foundation", "branded", "off"))
        )
    )

    assert state["maximum"] == 4
    assert [source.source for source in result.sources] == [
        "wikidata",
        "foundation",
        "branded",
        "off",
    ]
    assert result.total_records_indexed == 4


def test_wikidata_dlt_loader_runs_off_event_loop_and_uses_repository() -> None:
    main_thread = threading.get_ident()
    loader_thread: int | None = None
    saved: list[list[str]] = []

    def loader(**_kwargs):
        nonlocal loader_thread
        loader_thread = threading.get_ident()
        return object(), [
            FoodEntityRecord(id="Q1", label="One"),
            FoodEntityRecord(id="Q2", label="Two"),
            FoodEntityRecord(id="Q3", label="Three"),
        ]

    class Repository:
        async def save_records(self, batch: list[FoodEntityRecord]) -> None:
            saved.append([record.id for record in batch])

    result = asyncio.run(
        ingest_wikidata(
            Repository(),  # type: ignore[arg-type]
            IngestionConfig(
                foundation_archive=Path("unused"),
                branded_archive=Path("unused"),
                openfoodfacts_archive=Path("unused"),
                repository_batch_size=2,
            ),
            loader=loader,
        )
    )

    assert loader_thread is not None
    assert loader_thread != main_thread
    assert saved == [["Q1", "Q2"], ["Q3"]]
    assert result == SourceIngestionResult(source="wikidata", records_indexed=3)
