"""Create, validate, and publish immutable Elasticsearch ingestion snapshots."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from elasticsearch import AsyncElasticsearch


def _marker_path(staging_dir: Path, alias: str) -> Path:
    """Return the durable marker shared by separate Kestra stage processes."""
    return staging_dir / ".elasticsearch-snapshots" / f"{alias}.json"


def _read_marker(staging_dir: Path, alias: str) -> str | None:
    """Read the pending physical index name, if a prior indexing attempt exists."""
    path = _marker_path(staging_dir, alias)
    if not path.exists():
        return None
    return str(json.loads(path.read_text(encoding="utf-8"))["index"])


def _write_marker(staging_dir: Path, alias: str, index: str) -> None:
    """Persist a candidate index atomically for the later validation stage."""
    path = _marker_path(staging_dir, alias)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"index": index}), encoding="utf-8")
    temporary.replace(path)


def _active_index(alias_response: dict[str, Any], alias: str) -> str:
    """Select the write index behind an alias, accepting a single read alias too."""
    write_indices = [
        index
        for index, definition in alias_response.items()
        if definition.get("aliases", {}).get(alias, {}).get("is_write_index") is True
    ]
    if len(write_indices) == 1:
        return write_indices[0]
    if len(alias_response) == 1:
        return next(iter(alias_response))
    raise RuntimeError(f"Alias {alias!r} does not have exactly one active write index")


def _snapshot_settings(settings_response: dict[str, Any], index: str) -> dict[str, Any]:
    """Copy portable index settings while excluding generated Elasticsearch values."""
    source = settings_response[index]["settings"]["index"]
    keys = ("number_of_shards", "number_of_replicas", "refresh_interval", "analysis")
    return {key: source[key] for key in keys if key in source}


async def prepare_snapshot_index(
    client: AsyncElasticsearch,
    *,
    alias: str,
    staging_dir: Path,
) -> str:
    """Create a fresh unaliased physical index for one ingestion attempt."""
    aliases = cast(dict[str, Any], await client.indices.get_alias(name=alias))
    active = _active_index(aliases, alias)
    mappings = cast(dict[str, Any], await client.indices.get_mapping(index=active))
    settings = cast(dict[str, Any], await client.indices.get_settings(index=active))
    schema_version = mappings[active].get("mappings", {}).get("_meta", {}).get(
        "schema_version", "v1"
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    candidate = f"{alias}-{schema_version}-snapshot-{timestamp}-{uuid.uuid4().hex[:8]}"
    await client.indices.create(
        index=candidate,
        mappings=mappings[active]["mappings"],
        settings=_snapshot_settings(settings, active),
    )
    _write_marker(staging_dir, alias, candidate)
    return candidate


async def pending_snapshot_index(
    client: AsyncElasticsearch,
    *,
    alias: str,
    staging_dir: Path,
) -> str:
    """Return the candidate created by indexing, rejecting missing state."""
    candidate = _read_marker(staging_dir, alias)
    if candidate is None:
        raise RuntimeError(f"No pending Elasticsearch snapshot exists for {alias}")
    if not await client.indices.exists(index=candidate):
        raise RuntimeError(
            f"Pending Elasticsearch snapshot does not exist: {candidate}"
        )
    return candidate


async def publish_snapshot_index(
    client: AsyncElasticsearch,
    *,
    alias: str,
    candidate: str,
    staging_dir: Path,
    aggregate_alias: str = "food-entities",
) -> None:
    """Atomically move source and aggregate aliases to a validated candidate."""
    current_aliases = cast(
        dict[str, Any], await client.indices.get_alias(name=alias)
    )
    current_indices = list(current_aliases)
    actions: list[dict[str, Any]] = []
    for index in current_indices:
        if index == candidate:
            continue
        actions.append({"remove": {"index": index, "alias": alias}})
        actions.append(
            {
                "remove": {
                    "index": index,
                    "alias": aggregate_alias,
                    "must_exist": False,
                }
            }
        )
    if candidate not in current_indices:
        actions.extend(
            [
                {
                    "add": {
                        "index": candidate,
                        "alias": alias,
                        "is_write_index": True,
                    }
                },
                {"add": {"index": candidate, "alias": aggregate_alias}},
            ]
        )
    if actions:
        await client.indices.update_aliases(actions=actions)
    _marker_path(staging_dir, alias).unlink(missing_ok=True)
