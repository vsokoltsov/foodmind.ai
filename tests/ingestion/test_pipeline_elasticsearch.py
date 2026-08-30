import asyncio
import gzip
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from elasticsearch import Elasticsearch

from app.aggregates import FoodEntity
from app.ingestion.pipeline import IngestionConfig, run_ingestion

pytestmark = pytest.mark.integration


def _write_json_zip(path: Path, filename: str, payload: object) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr(filename, json.dumps(payload))


def test_all_sources_write_to_elasticsearch_in_one_pipeline(
    initialized_elasticsearch: str,
    tmp_path: Path,
) -> None:
    foundation_path = tmp_path / "foundation.json.zip"
    branded_path = tmp_path / "branded.json.zip"
    openfoodfacts_path = tmp_path / "openfoodfacts.jsonl.gz"

    _write_json_zip(
        foundation_path,
        "foundation.json",
        {
            "FoundationFoods": [
                {
                    "foodClass": "FinalFood",
                    "description": "Pipeline foundation food",
                    "foodNutrients": [],
                    "foodAttributes": [],
                    "foodCategory": {"description": "Test foods"},
                    "isHistoricalReference": False,
                    "ndbNumber": 900001,
                    "dataType": "Foundation",
                    "fdcId": 900001,
                    "publicationDate": "8/27/2026",
                }
            ]
        },
    )
    _write_json_zip(
        branded_path,
        "branded.json",
        {
            "BrandedFoods": [
                {
                    "foodClass": "Branded",
                    "description": "Pipeline branded food",
                    "foodNutrients": [],
                    "foodAttributes": [],
                    "modifiedDate": "8/27/2026",
                    "availableDate": "8/27/2026",
                    "marketCountry": "United States",
                    "brandOwner": "Pipeline Foods",
                    "dataSource": "LI",
                    "brandedFoodCategory": "Test foods",
                    "gtinUpc": "9999999999991",
                    "ingredients": "TEST INGREDIENT",
                    "servingSize": 10,
                    "servingSizeUnit": "g",
                    "householdServingFullText": "1 serving",
                    "labelNutrients": {},
                    "tradeChannels": [],
                    "microbes": [],
                    "foodUpdateLog": [],
                    "dataType": "Branded",
                    "fdcId": 900002,
                    "publicationDate": "8/27/2026",
                }
            ]
        },
    )
    with gzip.open(openfoodfacts_path, "wt", encoding="utf-8") as export:
        export.write(
            json.dumps(
                {
                    "code": "9999999999992",
                    "product_name": "Pipeline Open Food Facts product",
                    "brands": "Pipeline Foods",
                    "nutriments": {"energy-kcal_100g": 100},
                }
            )
            + "\n"
        )

    def wikidata_loader(**_kwargs):
        return object(), [
            FoodEntity(id="Q999999", label="Pipeline Wikidata food")
        ]

    result = asyncio.run(
        run_ingestion(
            IngestionConfig(
                elasticsearch_url=initialized_elasticsearch,
                foundation_archive=foundation_path,
                branded_archive=branded_path,
                openfoodfacts_archive=openfoodfacts_path,
                repository_batch_size=1,
            ),
            wikidata_loader=wikidata_loader,
        )
    )

    assert [(source.source, source.records_indexed) for source in result.sources] == [
        ("wikidata", 1),
        ("usda_foundation", 1),
        ("usda_branded", 1),
        ("openfoodfacts", 1),
    ]
    with Elasticsearch(initialized_elasticsearch) as client:
        assert client.get(
            index="wikidata-food-entities",
            id="wikidata:Q999999",
        )["_source"]["label"] == "Pipeline Wikidata food"
        assert client.get(
            index="usda-foundation-foods",
            id="usda-fdc:900001",
        )["_source"]["label"] == "Pipeline foundation food"
        assert client.get(
            index="usda-branded-foods",
            id="usda-fdc:900002",
        )["_source"]["label"] == "Pipeline branded food"
        assert client.get(
            index="openfoodfacts-products",
            id="openfoodfacts:9999999999992",
        )["_source"]["label"] == "Pipeline Open Food Facts product"
