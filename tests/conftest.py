import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from elasticsearch import Elasticsearch
from testcontainers.community.elasticsearch import ElasticSearchContainer

ELASTICSEARCH_IMAGE = (
    "docker.elastic.co/elasticsearch/elasticsearch:9.4.3"
)
PROJECT_ROOT = Path(__file__).parents[1]
INDEX_DEFINITIONS = {
    "wikidata-food-entities-v1": "wikidata-food-entities.json",
    "usda-foundation-foods-v1": "usda-foundation-foods.json",
    "usda-branded-foods-v1": "usda-branded-foods.json",
    "openfoodfacts-products-v1": "openfoodfacts-products.json",
}


@pytest.fixture(scope="session")
def elasticsearch_url() -> Iterator[str]:
    """Start one real Elasticsearch container for integration tests."""
    container = ElasticSearchContainer(ELASTICSEARCH_IMAGE, mem_limit="1g")
    container.with_env("ES_JAVA_OPTS", "-Xms512m -Xmx512m")

    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"http://{host}:{port}"


@pytest.fixture(scope="session")
def initialized_elasticsearch(elasticsearch_url: str) -> Iterator[str]:
    """Apply the generated v1 mappings and aliases to Elasticsearch."""
    generated = PROJECT_ROOT / "elasticsearch" / "generated" / "v1"

    with Elasticsearch(elasticsearch_url) as client:
        for index, filename in INDEX_DEFINITIONS.items():
            definition = json.loads((generated / filename).read_text())
            client.indices.create(
                index=index,
                mappings=definition["mappings"],
                settings=definition["settings"],
            )

        aliases = json.loads((generated / "aliases.json").read_text())
        client.indices.update_aliases(actions=aliases["actions"])
        yield elasticsearch_url
