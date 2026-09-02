"""Fixtures for the live food-search evaluation."""

from collections.abc import Iterator
import os

import pytest
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from app.settings import get_settings


EVALUATION_INDEXES = (
    "wikidata-food-entities",
    "usda-foundation-foods",
    "usda-branded-foods",
    "openfoodfacts-products",
)


@pytest.fixture
def evaluation_catalog() -> Iterator[str]:
    """Create a small, realistic catalog for the live agent evaluation.

    The fixture writes complete documents to the same aliases used by the
    repositories.  This keeps the evaluation deterministic while still
    exercising real Elasticsearch queries and the real LLM agent.
    """
    if not get_settings().OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for the live evaluation")
    url = get_settings().ELASTICSEARCH_URL
    client = Elasticsearch(url)
    try:
        try:
            available = client.ping()
        except Exception:
            if os.getenv("CI"):
                raise
            available = False
        if not available:
            pytest.skip("Elasticsearch is required for the live evaluation")
        for index in EVALUATION_INDEXES:
            if client.indices.exists(index=index):
                client.indices.delete(index=index)
            client.indices.create(index=index)

        documents = [
            {
                "_index": "wikidata-food-entities",
                "_id": "wikidata:Q161807",
                "_source": {
                    "id": "Q161807",
                    "label": "Italian pasta",
                    "description": "A traditional Italian food concept.",
                    "aliases": ["pasta"],
                    "countries": [],
                    "cuisines": [{"id": "Q119", "label": "Italian cuisine"}],
                    "instance_of": [],
                    "subclasses": [],
                    "images": [],
                    "articles": [],
                },
            },
            {
                "_index": "usda-foundation-foods",
                "_id": "usda-fdc:1001",
                "_source": {
                    "id": "usda-fdc:1001",
                    "source": "usda_fdc",
                    "entity_type": "foundation_food",
                    "label": "Apple, raw",
                    "description": "Raw apple with skin",
                    "fdc_id": 1001,
                    "category": "Fruits",
                    "scientific_name": None,
                    "publication_date": "2026-01-01",
                    "nutrients": [
                        {"id": 1003, "number": "203", "name": "Protein", "unit": "g", "amount": 0.26},
                        {"id": 1079, "number": "291", "name": "Fiber, total dietary", "unit": "g", "amount": 2.4},
                    ],
                },
            },
            {
                "_index": "usda-branded-foods",
                "_id": "usda-fdc:2001",
                "_source": {
                    "id": "usda-fdc:2001",
                    "source": "usda_fdc",
                    "entity_type": "branded_food",
                    "label": "Chocolate protein bar",
                    "description": "A chocolate flavored snack bar",
                    "fdc_id": 2001,
                    "category": "Snack bars",
                    "brand_owner": "Example Foods",
                    "brand_name": "Example",
                    "gtin_upc": "000000000001",
                    "ingredients": "Cocoa, oats",
                    "market_country": "United States",
                    "publication_date": "2026-01-01",
                    "serving_size": 40.0,
                    "serving_size_unit": "g",
                    "nutrients": [
                        {"id": 1003, "number": "203", "name": "Protein", "unit": "g", "amount": 10.0},
                        {"id": 1079, "number": "291", "name": "Fiber, total dietary", "unit": "g", "amount": 6.0},
                    ],
                },
            },
            {
                "_index": "openfoodfacts-products",
                "_id": "openfoodfacts:000000000002",
                "_source": {
                    "id": "openfoodfacts:000000000002",
                    "source": "openfoodfacts",
                    "entity_type": "product",
                    "label": "Apple juice",
                    "description": "Apple juice drink",
                    "code": "000000000002",
                    "brands": "Example Drinks",
                    "brands_tags": ["example-drinks"],
                    "categories": "Beverages",
                    "categories_tags": ["en:beverages"],
                    "countries": "United States",
                    "countries_tags": ["en:united-states"],
                    "ingredients": "Apple juice",
                    "ingredients_tags": ["en:apple"],
                    "allergens": None,
                    "allergens_tags": [],
                    "traces": None,
                    "traces_tags": [],
                    "labels_tags": [],
                    "quantity": "1 L",
                    "serving_size": None,
                    "nutrition_grade": None,
                    "nova_group": None,
                    "nutriments": {},
                    "image_url": None,
                    "image_front_url": None,
                    "last_modified_at": None,
                },
            },
        ]
        bulk(client, documents)
        client.indices.refresh(index="*")
        yield url
    finally:
        for index in EVALUATION_INDEXES:
            try:
                if client.indices.exists(index=index):
                    client.indices.delete(index=index)
            except Exception:
                # The client may be unavailable when setup is skipped locally.
                pass
        client.close()
