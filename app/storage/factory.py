"""Construction helpers for configured artifact stores."""

from typing import Literal

from app.storage.gcs import GCSArtifactStore
from app.storage.local import LocalArtifactStore
from app.storage.protocol import ArtifactStore


def create_artifact_store(
    backend: Literal["local", "gcs"],
    *,
    bucket: str | None = None,
    prefix: str = "foodmind/ingestion",
    project: str | None = None,
) -> ArtifactStore:
    """Build a local or Google Cloud Storage backend from runtime values."""
    match backend:
        case "gcs":
            return GCSArtifactStore(
                bucket or "",
                prefix=prefix,
                project=project,
            )
        case "local":
            return LocalArtifactStore()
