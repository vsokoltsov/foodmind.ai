"""Create the version-one Elasticsearch indexes and aliases."""

import json
from pathlib import Path

from elasticsearch import Elasticsearch

from app.settings import get_settings

revision = "20260903120000"
down_revision = None
branch_labels = None
depends_on = None

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "elasticsearch" / "generated" / "v1"
INDEXES = (
    "wikidata-food-entities",
    "usda-foundation-foods",
    "usda-branded-foods",
    "openfoodfacts-products",
)


def upgrade() -> None:
    """Create missing indexes and install missing aliases idempotently."""
    client = Elasticsearch(get_settings().ELASTICSEARCH_URL)
    try:
        for index in INDEXES:
            physical_index = f"{index}-v1"
            if client.indices.exists(index=physical_index):
                continue
            definition = json.loads(
                (GENERATED / f"{index}.json").read_text(encoding="utf-8")
            )
            client.indices.create(
                index=physical_index,
                settings=definition.get("settings"),
                mappings=definition.get("mappings"),
            )
        _apply_missing_aliases(client)
    finally:
        client.close()


def _apply_missing_aliases(client: Elasticsearch) -> None:
    """Add only aliases that do not already exist."""
    payload = json.loads((GENERATED / "aliases.json").read_text(encoding="utf-8"))
    actions = []
    for action in payload["actions"]:
        add = action.get("add")
        if add is None or not client.indices.exists_alias(name=add["alias"]):
            actions.append(action)
    if actions:
        client.indices.update_aliases(actions=actions)


def downgrade() -> None:
    """Remove version-one aliases and indexes when they exist."""
    client = Elasticsearch(get_settings().ELASTICSEARCH_URL)
    try:
        for index in INDEXES:
            physical_index = f"{index}-v1"
            if client.indices.exists_alias(name=index):
                client.indices.delete_alias(index="*", name=index)
            if client.indices.exists(index=physical_index):
                client.indices.delete(index=physical_index)
        if client.indices.exists_alias(name="food-entities"):
            client.indices.delete_alias(index="*", name="food-entities")
    finally:
        client.close()
