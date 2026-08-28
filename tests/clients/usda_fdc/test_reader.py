import json
from collections.abc import Callable
from pathlib import Path
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from app.clients.usda_fdc.reader import USDAFoodDataReader


@pytest.fixture
def reader() -> USDAFoodDataReader:
    """Provide a USDA archive reader."""
    return USDAFoodDataReader()


@pytest.fixture
def archive_factory(tmp_path: Path) -> Callable[[str, object], Path]:
    """Create a ZIP archive containing one JSON document."""
    def create(name: str, payload: object) -> Path:
        archive_path = tmp_path / f"{name}.json.zip"
        with ZipFile(archive_path, "w") as archive:
            archive.writestr(f"nested/{name}.json", json.dumps(payload))
        return archive_path

    return create


@pytest.fixture
def foundation_record() -> dict[str, object]:
    """Return a minimal record matching the Foundation Foods export."""
    return {
        "foodClass": "FinalFood",
        "description": "Hummus, commercial",
        "foodNutrients": [],
        "foodAttributes": [],
        "foodCategory": {"description": "Legumes and Legume Products"},
        "isHistoricalReference": False,
        "ndbNumber": 16158,
        "dataType": "Foundation",
        "fdcId": 321358,
        "publicationDate": "4/1/2019",
    }


@pytest.fixture
def branded_record() -> dict[str, object]:
    """Return a minimal record matching the Branded Foods export."""
    return {
        "foodClass": "Branded",
        "description": "SUPREME BASMATI RICE",
        "foodNutrients": [],
        "foodAttributes": [],
        "modifiedDate": "4/26/2020",
        "availableDate": "4/26/2020",
        "marketCountry": "United States",
        "brandOwner": "VEETEE",
        "dataSource": "LI",
        "brandedFoodCategory": "Rice",
        "gtinUpc": "8906004982514",
        "ingredients": "BASMATI RICE.",
        "servingSize": 45,
        "servingSizeUnit": "g",
        "householdServingFullText": "0.25 cup",
        "labelNutrients": {"calories": {"value": 160}},
        "tradeChannels": ["NO_TRADE_CHANNEL"],
        "microbes": [],
        "foodUpdateLog": [],
        "dataType": "Branded",
        "fdcId": 1106304,
        "publicationDate": "11/13/2020",
    }


def test_streams_foundation_foods_and_skips_null_records(
    reader: USDAFoodDataReader,
    archive_factory: Callable[[str, object], Path],
    foundation_record: dict[str, object],
) -> None:
    archive = archive_factory(
        "foundation",
        {"FoundationFoods": [foundation_record, None]},
    )

    foods = list(reader.iter_foundation_foods(archive))

    assert len(foods) == 1
    assert foods[0].fdc_id == 321358
    assert foods[0].description == "Hummus, commercial"


def test_streams_branded_foods(
    reader: USDAFoodDataReader,
    archive_factory: Callable[[str, object], Path],
    branded_record: dict[str, object],
) -> None:
    archive = archive_factory("branded", {"BrandedFoods": [branded_record]})

    foods = list(reader.iter_branded_foods(archive))

    assert len(foods) == 1
    assert foods[0].fdc_id == 1106304
    assert foods[0].label_nutrients.calories is not None
    assert foods[0].label_nutrients.calories.value == 160


def test_streams_branded_food_without_optional_dates(
    reader: USDAFoodDataReader,
    archive_factory: Callable[[str, object], Path],
    branded_record: dict[str, object],
) -> None:
    branded_record.pop("modifiedDate")
    branded_record.pop("availableDate")
    archive = archive_factory(
        "branded-without-dates",
        {"BrandedFoods": [branded_record]},
    )

    foods = list(reader.iter_branded_foods(archive))

    assert len(foods) == 1
    assert foods[0].fdc_id == 1106304
    assert foods[0].modified_date is None
    assert foods[0].available_date is None


def test_rejects_archive_without_exactly_one_json_file(
    reader: USDAFoodDataReader,
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "ambiguous.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("first.json", "{}")
        archive.writestr("second.json", "{}")

    with pytest.raises(ValueError, match="Expected exactly one JSON file"):
        list(reader.iter_foundation_foods(archive_path))


def test_propagates_record_validation_errors(
    reader: USDAFoodDataReader,
    archive_factory: Callable[[str, object], Path],
) -> None:
    archive = archive_factory(
        "invalid-foundation",
        {"FoundationFoods": [{"fdcId": 321358}]},
    )

    with pytest.raises(ValidationError):
        list(reader.iter_foundation_foods(archive))
