import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from elasticsearch import AsyncElasticsearch

from app.ingestion.elasticsearch_snapshots import (
    pending_snapshot_index,
    prepare_snapshot_index,
    publish_snapshot_index,
)


def _client() -> SimpleNamespace:
    indices = SimpleNamespace(
        exists=AsyncMock(return_value=False),
        get_alias=AsyncMock(
            return_value={
                "foods-v1": {
                    "aliases": {
                        "foods": {"is_write_index": True},
                    }
                }
            }
        ),
        get_mapping=AsyncMock(
            return_value={
                "foods-v1": {
                    "mappings": {
                        "_meta": {"schema_version": "v1"},
                        "dynamic": "strict",
                        "properties": {"id": {"type": "keyword"}},
                    }
                }
            }
        ),
        get_settings=AsyncMock(
            return_value={
                "foods-v1": {
                    "settings": {
                        "index": {
                            "number_of_shards": "1",
                            "number_of_replicas": "0",
                            "refresh_interval": "30s",
                            "uuid": "generated-value-must-not-be-copied",
                        }
                    }
                }
            }
        ),
        create=AsyncMock(),
        update_aliases=AsyncMock(),
    )
    return SimpleNamespace(indices=indices)


def test_prepare_snapshot_clones_mapping_and_persists_candidate(tmp_path: Path) -> None:
    client = _client()

    candidate = asyncio.run(
        prepare_snapshot_index(client, alias="foods", staging_dir=tmp_path)
    )

    assert candidate.startswith("foods-v1-snapshot-")
    create_call = client.indices.create.await_args.kwargs
    assert create_call["index"] == candidate
    assert create_call["mappings"]["dynamic"] == "strict"
    assert create_call["settings"] == {
        "number_of_shards": "1",
        "number_of_replicas": "0",
        "refresh_interval": "30s",
    }
    marker = tmp_path / ".elasticsearch-snapshots" / "foods.json"
    assert json.loads(marker.read_text()) == {"index": candidate}


def test_prepare_snapshot_replaces_stale_pending_marker(tmp_path: Path) -> None:
    client = _client()
    marker = tmp_path / ".elasticsearch-snapshots" / "foods.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({"index": "foods-v1-snapshot-existing"}))

    candidate = asyncio.run(
        prepare_snapshot_index(client, alias="foods", staging_dir=tmp_path)
    )

    assert candidate != "foods-v1-snapshot-existing"
    client.indices.create.assert_awaited_once()
    assert json.loads(marker.read_text()) == {"index": candidate}


def test_publish_snapshot_switches_aliases_atomically(tmp_path: Path) -> None:
    client = _client()
    candidate = "foods-v1-snapshot-new"
    marker = tmp_path / ".elasticsearch-snapshots" / "foods.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({"index": candidate}))

    asyncio.run(
        publish_snapshot_index(
            client,
            alias="foods",
            candidate=candidate,
            staging_dir=tmp_path,
        )
    )

    actions = client.indices.update_aliases.await_args.kwargs["actions"]
    assert {"remove": {"index": "foods-v1", "alias": "foods"}} in actions
    assert {
        "add": {
            "index": candidate,
            "alias": "foods",
            "is_write_index": True,
        }
    } in actions
    assert {"add": {"index": candidate, "alias": "food-entities"}} in actions
    assert not marker.exists()


def test_pending_snapshot_requires_existing_index(tmp_path: Path) -> None:
    client = _client()
    marker = tmp_path / ".elasticsearch-snapshots" / "foods.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({"index": "foods-v1-snapshot-new"}))

    try:
        asyncio.run(
            pending_snapshot_index(client, alias="foods", staging_dir=tmp_path)
        )
    except RuntimeError as error:
        assert "does not exist" in str(error)
    else:
        raise AssertionError("missing candidate index should fail")


@pytest.mark.integration
def test_snapshot_switch_keeps_previous_physical_index_for_rollback(
    initialized_elasticsearch: str,
    tmp_path: Path,
) -> None:
    async def scenario() -> tuple[str, dict, bool]:
        async with AsyncElasticsearch(initialized_elasticsearch) as client:
            candidate = await prepare_snapshot_index(
                client,
                alias="openfoodfacts-products",
                staging_dir=tmp_path,
            )
            await publish_snapshot_index(
                client,
                alias="openfoodfacts-products",
                candidate=candidate,
                staging_dir=tmp_path,
            )
            aliases = dict(
                await client.indices.get_alias(name="openfoodfacts-products")
            )
            previous_exists = bool(
                await client.indices.exists(index="openfoodfacts-products-v1")
            )
            await client.indices.update_aliases(
                actions=[
                    {
                        "remove": {
                            "index": candidate,
                            "alias": "openfoodfacts-products",
                        }
                    },
                    {
                        "remove": {
                            "index": candidate,
                            "alias": "food-entities",
                        }
                    },
                    {
                        "add": {
                            "index": "openfoodfacts-products-v1",
                            "alias": "openfoodfacts-products",
                            "is_write_index": True,
                        }
                    },
                    {
                        "add": {
                            "index": "openfoodfacts-products-v1",
                            "alias": "food-entities",
                        }
                    },
                ]
            )
            await client.indices.delete(index=candidate)
            return candidate, aliases, previous_exists

    candidate, aliases, previous_exists = asyncio.run(scenario())

    assert list(aliases) == [candidate]
    assert aliases[candidate]["aliases"]["openfoodfacts-products"][
        "is_write_index"
    ]
    assert previous_exists is True
