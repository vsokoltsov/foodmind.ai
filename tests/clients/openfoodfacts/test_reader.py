import gzip
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.clients.openfoodfacts.reader import OpenFoodFactsReader


@pytest.fixture
def reader() -> OpenFoodFactsReader:
    """Provide an Open Food Facts export reader."""
    return OpenFoodFactsReader()


@pytest.fixture
def export_factory(tmp_path: Path) -> Callable[[list[object]], Path]:
    """Create a gzip-compressed JSON Lines export."""
    def create(records: list[object]) -> Path:
        export_path = tmp_path / "openfoodfacts-products.jsonl.gz"
        with gzip.open(export_path, "wt", encoding="utf-8") as export:
            for record in records:
                if isinstance(record, str):
                    export.write(record)
                else:
                    export.write(json.dumps(record))
                export.write("\n")
        return export_path

    return create


@pytest.fixture
def product_record() -> dict[str, object]:
    """Return a representative subset of an Open Food Facts record."""
    return {
        "code": "0000101209159",
        "product_name": "Hazelnut and dark chocolate spread",
        "brands": "Bovetti",
        "brands_tags": ["xx:bovetti"],
        "categories_tags": ["en:spreads", "en:hazelnut-spreads"],
        "countries_tags": ["en:france"],
        "ingredients_text": "Hazelnuts, cocoa, sugar",
        "ingredients_tags": ["en:hazelnut", "en:cocoa", "en:sugar"],
        "allergens_tags": ["en:nuts"],
        "nutrition_grades": "e",
        "nova_group": 3,
        "nutriments": {
            "energy-kcal_100g": 617,
            "fat_100g": 48.0,
            "salt_100g": 0.01,
            "nutrition-score-fr_100g": None,
        },
        "image_front_url": "https://images.openfoodfacts.org/front.jpg",
        "last_modified_t": 1786042527,
        "schema_version": 1004,
        "large_unmodeled_section": {"ignored": True},
    }


def test_streams_and_validates_products(
    reader: OpenFoodFactsReader,
    export_factory: Callable[[list[object]], Path],
    product_record: dict[str, object],
) -> None:
    export_path = export_factory([product_record, "", product_record])

    products = list(reader.iter_products(export_path))

    assert len(products) == 2
    assert products[0].code == "0000101209159"
    assert products[0].product_name == "Hazelnut and dark chocolate spread"
    assert products[0].nutriments["energy-kcal_100g"] == 617
    assert products[0].model_extra is None


def test_reader_is_lazy_and_does_not_parse_the_whole_export_at_once(
    reader: OpenFoodFactsReader,
    export_factory: Callable[[list[object]], Path],
    product_record: dict[str, object],
) -> None:
    export_path = export_factory([product_record, "not-json"])

    products = reader.iter_products(export_path)

    assert next(products).code == "0000101209159"
    with pytest.raises(ValueError, match="at line 2"):
        next(products)


def test_propagates_product_validation_errors(
    reader: OpenFoodFactsReader,
    export_factory: Callable[[list[object]], Path],
) -> None:
    export_path = export_factory([{"product_name": "Missing barcode"}])

    with pytest.raises(ValidationError):
        next(reader.iter_products(export_path))
