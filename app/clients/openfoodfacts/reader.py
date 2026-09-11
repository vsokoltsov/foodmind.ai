"""Streaming reader for Open Food Facts gzip-compressed JSON Lines exports."""

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from app.clients.openfoodfacts.models import OpenFoodFactsProduct


class OpenFoodFactsReader:
    """Stream and validate products without loading the export into memory."""

    def iter_products(
        self,
        archive_path: Path,
    ) -> Iterator[OpenFoodFactsProduct]:
        """Yield validated products from a gzip-compressed JSON Lines export.

        Args:
            archive_path: Path to the downloaded ``.jsonl.gz`` export.

        Yields:
            One validated Open Food Facts product per non-empty input line.

        Raises:
            ValueError: If an input line does not contain valid JSON.
            pydantic.ValidationError: If a record does not match the product
                model.
        """
        with archive_path.open("rb") as compressed_export:
            yield from self.iter_products_stream(
                compressed_export,
                source_name=str(archive_path),
            )

    def iter_products_stream(
        self,
        compressed_export: BinaryIO,
        *,
        source_name: str,
    ) -> Iterator[OpenFoodFactsProduct]:
        """Yield products directly from a compressed binary object stream."""
        with gzip.GzipFile(fileobj=compressed_export, mode="rb") as export:
            for line_number, line in enumerate(export, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON in {source_name} at line {line_number}"
                    ) from error

                yield OpenFoodFactsProduct.model_validate(record)
