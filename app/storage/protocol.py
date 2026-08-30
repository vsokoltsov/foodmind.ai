"""Common interface for ingestion artifact storage backends."""

from pathlib import Path
from typing import Protocol


class ArtifactStore(Protocol):
    """Store and materialize downloaded ingestion artifacts."""

    async def exists(self, key: str) -> bool:
        """Return whether an artifact exists under ``key``."""

    async def upload(self, local_path: Path, key: str) -> None:
        """Upload a local artifact under ``key``."""

    async def download(self, key: str, destination: Path) -> Path:
        """Materialize an artifact at ``destination`` and return that path."""
