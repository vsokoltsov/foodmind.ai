"""Streaming reader for Open Food Facts gzip-compressed JSON Lines exports."""

import gzip
import json
from collections.abc import Iterator
from pathlib import Path

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
        with gzip.open(archive_path, "rb") as export:
            for line_number, line in enumerate(export, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON in {archive_path} at line {line_number}"
                    ) from error

                yield OpenFoodFactsProduct.model_validate(record)
