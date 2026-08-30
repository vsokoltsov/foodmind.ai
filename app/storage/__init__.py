"""Artifact storage backends used by ingestion."""

from app.storage.gcs import GCSArtifactStore
from app.storage.local import LocalArtifactStore
from app.storage.protocol import ArtifactStore

__all__ = ["ArtifactStore", "GCSArtifactStore", "LocalArtifactStore"]
