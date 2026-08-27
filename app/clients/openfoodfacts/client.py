"""HTTP client for downloading the Open Food Facts product export."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx
from tqdm import tqdm

from app.clients.openfoodfacts.models import DownloadArtifact


def _content_length(response: httpx.Response) -> int | None:
    """Return a valid response content length when the server provides one."""
    value = response.headers.get("Content-Length")
    if value is None:
        return None

    try:
        length = int(value)
    except ValueError:
        return None

    return length if length >= 0 else None


@dataclass
class OpenFoodFactsClient:
    """Download the compressed Open Food Facts JSON Lines export."""

    client: httpx.AsyncClient
    url: str = "https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz"

    @property
    def header(self) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _download_file(
        self,
        destination: Path,
        *,
        show_progress: bool,
    ) -> tuple[int, str]:
        """Download atomically and return its byte size and SHA-256 digest."""
        temp_destination = destination.with_suffix(destination.suffix + ".tmp")
        digest = hashlib.sha256()
        downloaded_bytes = 0

        try:
            async with self.client.stream("GET", self.url, headers=self.header) as response:
                response.raise_for_status()
                with (
                    temp_destination.open("wb") as output,
                    tqdm(
                        total=_content_length(response),
                        desc=destination.name,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        disable=not show_progress,
                    ) as progress,
                ):
                    # Raw bytes preserve the compressed export exactly as served.
                    async for chunk in response.aiter_raw():
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded_bytes += len(chunk)
                        progress.update(len(chunk))

            temp_destination.replace(destination)
        except BaseException:
            temp_destination.unlink(missing_ok=True)
            raise

        return downloaded_bytes, digest.hexdigest()

    async def get_facts(
        self,
        destination_path: str,
        *,
        show_progress: bool = False,
    ) -> DownloadArtifact:
        """Download the product export, optionally displaying progress and ETA."""
        dest_file = Path(destination_path)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        size_bytes, sha256 = await self._download_file(
            destination=dest_file,
            show_progress=show_progress,
        )
        return DownloadArtifact(
            source_url=self.url,
            path=dest_file,
            size_bytes=size_bytes,
            sha256=sha256,
        )
