"""Tests for independently executable ingestion stages."""

import asyncio
from pathlib import Path

import pytest

from app.ingestion.staged import (
    StagedIngestionConfig,
    _parquet_paths,
    download_source,
    process_source_batches,
    source_pipeline_lock,
)


class ArtifactStore:
    """Minimal artifact store double that records archive restoration."""

    def __init__(self, *, remote_exists: bool = True) -> None:
        """Create an artifact store containing one remote archive."""
        self.remote_exists = remote_exists
        self.downloaded: list[tuple[str, Path]] = []
        self.uploaded: list[tuple[Path, str]] = []

    async def exists(self, key: str) -> bool:
        """Report that the archive already exists remotely."""
        return self.remote_exists and key == "usda-foundation/foundations.json.zip"

    async def upload(self, local_path: Path, key: str) -> None:
        """Record an upload request."""
        self.uploaded.append((local_path, key))

    async def download(self, key: str, destination: Path) -> Path:
        """Materialize the remote archive locally."""
        self.downloaded.append((key, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"archive")
        return destination


@pytest.fixture
def artifact_store() -> ArtifactStore:
    """Return a remote artifact store test double."""
    return ArtifactStore()


def test_download_stage_keeps_existing_gcs_artifact_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_store: ArtifactStore,
) -> None:
    """An existing GCS archive must not consume pod-local ephemeral storage."""
    monkeypatch.setattr(
        "app.ingestion.staged.create_artifact_store",
        lambda _config: artifact_store,
    )
    archive = tmp_path / "data" / "foundations.json.zip"

    result = asyncio.run(
        download_source(
            "usda-foundation",
            StagedIngestionConfig(foundation_archive=archive, artifact_storage="gcs"),
        )
    )

    assert result == archive
    assert not archive.exists()
    assert artifact_store.downloaded == []
    assert artifact_store.uploaded == []


def test_download_stage_refuses_a_pod_local_gcs_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing remote export must fail instead of filling ephemeral storage."""
    artifact_store = ArtifactStore(remote_exists=False)
    monkeypatch.setattr(
        "app.ingestion.staged.create_artifact_store",
        lambda _config: artifact_store,
    )

    with pytest.raises(FileNotFoundError, match="upload it"):
        asyncio.run(
            download_source(
                "usda-foundation",
                StagedIngestionConfig(
                    foundation_archive=tmp_path / "foundations.json.zip",
                    artifact_storage="gcs",
                ),
            )
        )

    assert artifact_store.downloaded == []
    assert artifact_store.uploaded == []


def test_source_pipeline_lock_rejects_a_concurrent_stage(tmp_path: Path) -> None:
    """A duplicate Kestra retry must not mutate the same dlt pipeline."""
    config = StagedIngestionConfig(pipelines_dir=tmp_path / "pipelines")

    with (
        source_pipeline_lock("openfoodfacts", config),
        pytest.raises(RuntimeError, match="already running"),
    ):
        with source_pipeline_lock("openfoodfacts", config):
            pass


def test_process_source_batches_writes_small_durable_parquet_loads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each bounded source batch must become a standalone Parquet load."""
    records = [
        {"id": "one", "label": "One", "code": "one"},
        {"id": "two", "label": "Two", "code": "two"},
        {"id": "three", "label": "Three", "code": "three"},
    ]
    monkeypatch.setattr(
        "app.ingestion.staged._archive_documents",
        lambda _source, _config: iter(records),
    )
    config = StagedIngestionConfig(
        openfoodfacts_archive=tmp_path / "openfoodfacts.jsonl.gz",
        pipelines_dir=tmp_path / "pipelines",
        staging_dir=tmp_path / "state",
        normalized_dir=tmp_path / "normalized",
        source_batch_size=2,
    )
    config.openfoodfacts_archive.write_bytes(b"source-v1")

    assert process_source_batches("openfoodfacts", config) == 3
    assert len(_parquet_paths("openfoodfacts", config)) == 2
    # A retry skips the two durable dlt packages rather than appending the
    # first two source batches a second time.
    assert process_source_batches("openfoodfacts", config) == 0
    assert len(_parquet_paths("openfoodfacts", config)) == 2


def test_process_source_batches_discards_pre_parquet_duckdb_pending_packages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A one-time destination migration must not retry incompatible dlt jobs."""
    monkeypatch.setattr(
        "app.ingestion.staged._archive_documents",
        lambda _source, _config: iter([{"id": "one", "label": "One", "code": "one"}]),
    )
    config = StagedIngestionConfig(
        openfoodfacts_archive=tmp_path / "openfoodfacts.jsonl.gz",
        pipelines_dir=tmp_path / "pipelines",
        staging_dir=tmp_path / "state",
        normalized_dir=tmp_path / "normalized",
    )
    config.openfoodfacts_archive.write_bytes(b"source-v1")
    legacy_job = (
        config.pipelines_dir
        / "openfoodfacts_products"
        / "load"
        / "normalized"
        / "legacy"
        / "started_jobs"
        / "openfoodfacts_documents.legacy.insert_values.gz"
    )
    legacy_job.parent.mkdir(parents=True)
    legacy_job.write_bytes(b"legacy")

    assert process_source_batches("openfoodfacts", config) == 1
    assert not legacy_job.exists()
    assert len(_parquet_paths("openfoodfacts", config)) == 1


def test_changed_source_generation_uses_a_new_parquet_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replaced upstream archive must never append to the preceding snapshot."""
    archive = tmp_path / "openfoodfacts.jsonl.gz"
    records = [{"id": "one", "label": "One", "code": "one"}]
    monkeypatch.setattr(
        "app.ingestion.staged._archive_documents",
        lambda _source, _config: iter(records),
    )
    config = StagedIngestionConfig(
        openfoodfacts_archive=archive,
        pipelines_dir=tmp_path / "pipelines",
        staging_dir=tmp_path / "state",
        normalized_dir=tmp_path / "normalized",
        source_batch_size=1,
    )
    archive.write_bytes(b"source-v1")
    assert process_source_batches("openfoodfacts", config) == 1
    first_paths = _parquet_paths("openfoodfacts", config)

    archive.write_bytes(b"source-version-two")
    assert process_source_batches("openfoodfacts", config) == 1
    second_paths = _parquet_paths("openfoodfacts", config)

    assert first_paths != second_paths
    assert all("runs/openfoodfacts" in str(path) for path in second_paths)


def test_changed_batch_size_uses_a_new_parquet_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tuning change must not mix new Parquet batches with an older layout."""
    archive = tmp_path / "openfoodfacts.jsonl.gz"
    archive.write_bytes(b"source-v1")
    records = [{"id": "one", "label": "One", "code": "one"}]
    monkeypatch.setattr(
        "app.ingestion.staged._archive_documents",
        lambda _source, _config: iter(records),
    )
    common = {
        "openfoodfacts_archive": archive,
        "pipelines_dir": tmp_path / "pipelines",
        "staging_dir": tmp_path / "state",
        "normalized_dir": tmp_path / "normalized",
    }

    first_config = StagedIngestionConfig(**common, source_batch_size=1)
    assert process_source_batches("openfoodfacts", first_config) == 1
    first_paths = _parquet_paths("openfoodfacts", first_config)

    second_config = StagedIngestionConfig(**common, source_batch_size=2)
    assert process_source_batches("openfoodfacts", second_config) == 1
    second_paths = _parquet_paths("openfoodfacts", second_config)

    assert first_paths != second_paths
