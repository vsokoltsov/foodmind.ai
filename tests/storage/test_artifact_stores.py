import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

from app.storage.gcs import GCSArtifactStore
from app.storage.local import LocalArtifactStore


def test_local_store_keeps_existing_artifact(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "destination.json"
    source.write_text("artifact", encoding="utf-8")
    store = LocalArtifactStore()

    assert asyncio.run(store.exists(str(source))) is True
    asyncio.run(store.upload(source, str(source)))
    assert asyncio.run(store.download(str(source), destination)) == destination
    assert destination.read_text(encoding="utf-8") == "artifact"


def test_gcs_store_uses_prefixed_object_and_async_threads(tmp_path: Path) -> None:
    blob = Mock()
    blob.exists.return_value = True
    bucket = Mock()
    bucket.blob.return_value = blob
    client = Mock()
    client.bucket.return_value = bucket

    with patch("app.storage.gcs.storage.Client", return_value=client):
        store = GCSArtifactStore("foodmind-artifacts", prefix="foodmind/ingestion")
        assert asyncio.run(store.exists("openfoodfacts/products.jsonl.gz")) is True
        local = tmp_path / "products.gz"
        asyncio.run(store.upload(local, "openfoodfacts/products.jsonl.gz"))
        asyncio.run(store.download("openfoodfacts/products.jsonl.gz", local))

    bucket.blob.assert_called_with("foodmind/ingestion/openfoodfacts/products.jsonl.gz")
    blob.upload_from_filename.assert_called_once_with(str(local))
    blob.download_to_filename.assert_called_once_with(str(local))
