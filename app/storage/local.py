"""Local filesystem artifact storage."""

import asyncio
import shutil
from pathlib import Path


class LocalArtifactStore:
    """Keep ingestion artifacts on the local filesystem."""

    async def exists(self, key: str) -> bool:
        """Return whether the local artifact path exists."""
        return await asyncio.to_thread(Path(key).exists)

    async def upload(self, local_path: Path, key: str) -> None:
        """Keep the artifact at its existing local path.

        The local backend intentionally performs no copy because ``local_path``
        is already the durable location used by the local ingestion setup.
        """
        return None

    async def download(self, key: str, destination: Path) -> Path:
        """Copy a local artifact to ``destination`` when paths differ."""
        source = Path(key)
        if source != destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.copyfile, source, destination)
        return destination
