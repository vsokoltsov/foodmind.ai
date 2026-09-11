"""Streaming reader for USDA FoodData Central JSON ZIP archives."""

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, TypeVar
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

    def iter_foundation_foods_stream(
        self, compressed_export: BinaryIO, *, source_name: str
    ) -> Iterator[FoundationFood]:
        """Yield Foundation Foods directly from a seekable remote ZIP stream."""
        yield from self._iter_foods_stream(
            compressed_export,
            source_name=source_name,
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

    def iter_branded_foods_stream(
        self, compressed_export: BinaryIO, *, source_name: str
    ) -> Iterator[BrandedFood]:
        """Yield Branded Foods directly from a seekable remote ZIP stream."""
        yield from self._iter_foods_stream(
            compressed_export,
            source_name=source_name,
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
        with archive_path.open("rb") as compressed_export:
            yield from self._iter_foods_stream(
                compressed_export,
                source_name=str(archive_path),
                collection=collection,
                model=model,
            )

    def _iter_foods_stream(
        self,
        compressed_export: BinaryIO,
        *,
        source_name: str,
        collection: str,
        model: type[FoodModelT],
    ) -> Iterator[FoodModelT]:
        """Stream one collection from an open local or remote ZIP file."""
        with ZipFile(compressed_export) as archive:
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
                    f"Expected exactly one JSON file in {source_name}, found {names}"
                )

            with archive.open(json_members[0]) as json_file:
                records = ijson.items(json_file, f"{collection}.item")
                for record in records:
                    # The April 2026 Foundation export contains null placeholders.
                    if record is not None:
                        yield model.model_validate(record)
