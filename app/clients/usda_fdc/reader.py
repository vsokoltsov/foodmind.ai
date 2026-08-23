"""Streaming reader for USDA FoodData Central JSON ZIP archives."""

from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar
from zipfile import ZipFile

import ijson
from pydantic import BaseModel

from app.clients.usda_fdc.models import BrandedFood, FoundationFood

FoodModelT = TypeVar("FoodModelT", bound=BaseModel)


class USDAFoodDataReader:
    """Stream and validate food records without loading an archive into memory."""

    def iter_foundation_foods(self, archive_path: Path) -> Iterator[FoundationFood]:
        """Yield validated Foundation Food records from a USDA archive.

        Args:
            archive_path: Path to the downloaded Foundation Foods ZIP archive.

        Yields:
            Validated Foundation Food records. JSON null placeholders are skipped.
        """
        yield from self._iter_foods(
            archive_path,
            collection="FoundationFoods",
            model=FoundationFood,
        )

    def iter_branded_foods(self, archive_path: Path) -> Iterator[BrandedFood]:
        """Yield validated Branded Food records from a USDA archive.

        Args:
            archive_path: Path to the downloaded Branded Foods ZIP archive.

        Yields:
            Validated Branded Food records.
        """
        yield from self._iter_foods(
            archive_path,
            collection="BrandedFoods",
            model=BrandedFood,
        )

    def _iter_foods(
        self,
        archive_path: Path,
        *,
        collection: str,
        model: type[FoodModelT],
    ) -> Iterator[FoodModelT]:
        """Stream one USDA collection and validate each non-null record."""
        with ZipFile(archive_path) as archive:
            json_members = [
                member
                for member in archive.infolist()
                if not member.is_dir()
                and not member.filename.startswith("__MACOSX/")
                and member.filename.lower().endswith(".json")
            ]
            if len(json_members) != 1:
                names = [member.filename for member in json_members]
                raise ValueError(
                    f"Expected exactly one JSON file in {archive_path}, found {names}"
                )

            with archive.open(json_members[0]) as json_file:
                records = ijson.items(json_file, f"{collection}.item")
                for record in records:
                    # The April 2026 Foundation export contains null placeholders.
                    if record is not None:
                        yield model.model_validate(record)
