"""Google Cloud Storage artifact backend."""

import asyncio
from pathlib import Path

from google.cloud import storage


class GCSArtifactStore:
    """Store ingestion artifacts in a Google Cloud Storage bucket."""

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "foodmind/ingestion",
        project: str | None = None,
    ) -> None:
        """Create a GCS store using Application Default Credentials."""
        if not bucket:
            raise ValueError("A GCS bucket is required for the GCS artifact store")
        self._client = storage.Client(project=project)
        self._bucket = self._client.bucket(bucket)
        self._prefix = prefix.strip("/")

    def _blob(self, key: str):
        """Return a bucket blob with the configured prefix applied."""
        object_name = "/".join(part for part in (self._prefix, key.strip("/")) if part)
        return self._bucket.blob(object_name)

    async def exists(self, key: str) -> bool:
        """Return whether the object exists in GCS."""
        return await asyncio.to_thread(self._blob(key).exists)

    async def upload(self, local_path: Path, key: str) -> None:
        """Upload a local artifact using resumable transfers for large files."""
        blob = self._blob(key)
        blob.chunk_size = 8 * 1024 * 1024
        await asyncio.to_thread(blob.upload_from_filename, str(local_path))

    async def download(self, key: str, destination: Path) -> Path:
        """Download an object to a local path for a reader stage."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._blob(key).download_to_filename, str(destination))
        return destination
