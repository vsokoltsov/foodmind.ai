import asyncio
from pathlib import Path
from urllib.parse import parse_qs

import dlt
import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.aggregates import FoodEntity
from app.ingestion.models import (
    WikidataAliasRecord,
    WikidataEntityRecord,
    WikidataMediaArticleRecord,
    WikidataOriginRecord,
    WikidataTaxonomyRecord,
)
from app.ingestion.wikidata_food_entities import (
    _read_models,
    normalize_food_entity_records,
    run_pipeline_stages,
)

WIKIDATA_URL = "https://query.wikidata.org/sparql"
ITEM = {"type": "uri", "value": "http://www.wikidata.org/entity/Q123"}


@pytest.fixture
def wikidata_server(httpx_mock: HTTPXMock) -> tuple[HTTPXMock, dict[str, int]]:
    """Mock every Wikidata endpoint response used by the ingestion join."""
    literal = {"type": "literal", "value": "Test food", "xml:lang": "en"}
    concurrency = {"active": 0, "maximum": 0}

    async def respond(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.content.decode())["query"][0]
        if "wdt:P279* wd:Q2095" in query:
            bindings = [
                {
                    "item": ITEM,
                    "itemLabel": literal,
                    "itemDescription": {
                        "type": "literal",
                        "value": "A food used for ingestion tests",
                        "xml:lang": "en",
                    },
                }
            ]
        else:
            concurrency["active"] += 1
            concurrency["maximum"] = max(
                concurrency["maximum"],
                concurrency["active"],
            )
            # An async response delay makes overlapping detail resources observable.
            await asyncio.sleep(0.02)
            concurrency["active"] -= 1

            if "skos:altLabel" in query:
                alias = {
                    "item": ITEM,
                    "alias": {
                        "type": "literal",
                        "value": "Test dish",
                        "xml:lang": "en",
                    },
                }
                # Repeated facts verify that the final join deduplicates values.
                bindings = [alias, alias]
            elif "wdt:P31" in query:
                bindings = [
                    {
                        "item": ITEM,
                        "instance": {
                            "type": "uri",
                            "value": "http://www.wikidata.org/entity/Q2095",
                        },
                        "instanceLabel": {
                            "type": "literal",
                            "value": "Food",
                            "xml:lang": "en",
                        },
                        "subclass": {
                            "type": "uri",
                            "value": "http://www.wikidata.org/entity/Q25403900",
                        },
                        "subclassLabel": {
                            "type": "literal",
                            "value": "Food ingredient",
                            "xml:lang": "en",
                        },
                    }
                ]
            elif "wdt:P495" in query:
                bindings = [
                    {
                        "item": ITEM,
                        "country": {
                            "type": "uri",
                            "value": "http://www.wikidata.org/entity/Q38",
                        },
                        "countryLabel": {
                            "type": "literal",
                            "value": "Italy",
                            "xml:lang": "en",
                        },
                        "cuisine": {
                            "type": "uri",
                            "value": "http://www.wikidata.org/entity/Q192786",
                        },
                        "cuisineLabel": {
                            "type": "literal",
                            "value": "Italian cuisine",
                            "xml:lang": "en",
                        },
                    }
                ]
            elif "wdt:P18" in query:
                bindings = [
                    {
                        "item": ITEM,
                        "image": {
                            "type": "uri",
                            "value": "https://commons.wikimedia.org/Food.jpg",
                        },
                        "article": {
                            "type": "uri",
                            "value": "https://en.wikipedia.org/wiki/Test_food",
                        },
                    }
                ]
            else:
                raise AssertionError(f"Unexpected SPARQL query: {query}")

        return httpx.Response(200, json={"results": {"bindings": bindings}})

    httpx_mock.add_callback(
        respond,
        method="POST",
        url=WIKIDATA_URL,
        is_reusable=True,
    )
    return httpx_mock, concurrency


def test_normalizes_staged_rows_into_one_complete_record() -> None:
    records = normalize_food_entity_records(
        entities=[
            WikidataEntityRecord(
                id="Q123",
                label="Test food",
                description="A food used for ingestion tests",
            )
        ],
        aliases=[
            WikidataAliasRecord(item_id="Q123", alias="Test dish"),
            WikidataAliasRecord(item_id="Q123", alias="Test dish"),
        ],
        taxonomy=[
            WikidataTaxonomyRecord(
                item_id="Q123",
                instance_id="Q2095",
                instance_label="Food",
                subclass_id="Q25403900",
                subclass_label="Food ingredient",
            )
        ],
        origins=[
            WikidataOriginRecord(
                item_id="Q123",
                country_id="Q38",
                country_label="Italy",
                cuisine_id="Q192786",
                cuisine_label="Italian cuisine",
            )
        ],
        media_articles=[
            WikidataMediaArticleRecord(
                item_id="Q123",
                image="https://commons.wikimedia.org/Food.jpg",
                article="https://en.wikipedia.org/wiki/Test_food",
            )
        ],
    )

    assert [record.model_dump(exclude_none=True) for record in records] == [
        {
            "id": "Q123",
            "label": "Test food",
            "description": "A food used for ingestion tests",
            "aliases": ["Test dish"],
            "countries": [{"id": "Q38", "label": "Italy"}],
            "cuisines": [{"id": "Q192786", "label": "Italian cuisine"}],
            "instance_of": [{"id": "Q2095", "label": "Food"}],
            "subclasses": [{"id": "Q25403900", "label": "Food ingredient"}],
            "images": ["https://commons.wikimedia.org/Food.jpg"],
            "articles": ["https://en.wikipedia.org/wiki/Test_food"],
        }
    ]


def test_dlt_resource_loads_normalized_record_into_duckdb(
    tmp_path: Path,
    wikidata_server: tuple[HTTPXMock, dict[str, int]],
) -> None:
    httpx_mock, concurrency = wikidata_server
    destination = dlt.destinations.duckdb(
        credentials=str(tmp_path / "foodmind.duckdb")
    )
    pipeline = dlt.pipeline(
        pipeline_name="wikidata_food_entities_test",
        pipelines_dir=str(tmp_path / "pipelines"),
        destination=destination,
        dataset_name="foodmind_test",
    )

    load_info = run_pipeline_stages(pipeline)

    assert not load_info.entities.has_failed_jobs
    assert load_info.details is not None
    assert not load_info.details.has_failed_jobs
    assert not load_info.normalized.has_failed_jobs
    with pipeline.sql_client() as sql_client:
        normalized_rows = sql_client.execute_sql(
            'SELECT id, label, description FROM "foodmind_test"."food_entities"'
        )
        staged_tables = sql_client.execute_sql(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'foodmind_test'
              AND table_name LIKE 'wikidata_%'
            ORDER BY table_name
            """
        )
    assert normalized_rows == [
        ("Q123", "Test food", "A food used for ingestion tests"),
    ]
    assert _read_models(pipeline, "food_entities", FoodEntity) == [
        FoodEntity(
            id="Q123",
            label="Test food",
            description="A food used for ingestion tests",
            aliases=["Test dish"],
            countries=[{"id": "Q38", "label": "Italy"}],
            cuisines=[{"id": "Q192786", "label": "Italian cuisine"}],
            instance_of=[{"id": "Q2095", "label": "Food"}],
            subclasses=[{"id": "Q25403900", "label": "Food ingredient"}],
            images=["https://commons.wikimedia.org/Food.jpg"],
            articles=["https://en.wikipedia.org/wiki/Test_food"],
        )
    ]
    assert staged_tables == [
        ("wikidata_aliases",),
        ("wikidata_entities",),
        ("wikidata_media_articles",),
        ("wikidata_origins",),
        ("wikidata_taxonomy",),
    ]
    assert len(httpx_mock.get_requests()) == 5
    assert concurrency["maximum"] == 4
