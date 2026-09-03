"""Versioned storage and loading of evaluation-selected configurations."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.settings import get_settings
from app.storage.gcs import GCSArtifactStore
from app.storage.local import LocalArtifactStore
from app.storage.protocol import ArtifactStore


class EvaluationArtifact(BaseModel):
    """Persisted evaluation result and runtime strategy selection."""

    name: str
    best_approach: str
    summary: list[dict[str, Any]]


class EvaluationArtifactRepository:
    """Store evaluation reports locally or in the configured GCS bucket."""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        """Create a repository using GCS when an evaluation bucket is configured."""
        settings = get_settings()
        self._prefix = settings.EVALUATION_ARTIFACT_PREFIX.strip("/")
        self._local_root = Path("evaluation-artifacts")
        self._store = store or (
            GCSArtifactStore(
                settings.EVALUATION_ARTIFACT_BUCKET,
                prefix=self._prefix,
                project=settings.GCP_PROJECT_ID,
            )
            if settings.EVALUATION_ARTIFACT_BUCKET
            else LocalArtifactStore()
        )

    def _key(self, name: str) -> str:
        """Return the versioned object key for an evaluation name."""
        return f"{name}/latest.json"

    async def save(
        self,
        name: str,
        summary: list[dict[str, Any]],
        best_approach: str,
    ) -> EvaluationArtifact:
        """Persist a report and its selected strategy."""
        artifact = EvaluationArtifact(
            name=name, best_approach=best_approach, summary=summary
        )
        if isinstance(self._store, LocalArtifactStore):
            destination = self._local_root / self._key(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        else:
            temporary = self._local_root / self._key(name)
            temporary.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
            await self._store.upload(temporary, self._key(name))
        return artifact

    async def load(self, name: str) -> EvaluationArtifact:
        """Load the latest evaluation configuration for a strategy name."""
        key = self._key(name)
        destination = self._local_root / key
        if isinstance(self._store, LocalArtifactStore):
            payload = json.loads(destination.read_text(encoding="utf-8"))
        else:
            await self._store.download(key, destination)
            payload = json.loads(destination.read_text(encoding="utf-8"))
        return EvaluationArtifact.model_validate(payload)
