"""HTTP client for downloading the Open Food Facts product export."""

import asyncio
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
    max_download_attempts: int = 4
    retry_delay_seconds: float = 2.0

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
        """Download atomically, resuming a persistent partial file when possible."""
        temp_destination = destination.with_suffix(destination.suffix + ".tmp")
        last_error: BaseException | None = None
        for attempt in range(1, self.max_download_attempts + 1):
            try:
                return await self._download_attempt(
                    destination,
                    temp_destination=temp_destination,
                    show_progress=show_progress,
                )
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                if isinstance(error, httpx.HTTPStatusError):
                    status = error.response.status_code
                    if status not in {408, 429} and status < 500:
                        raise
                last_error = error
                if attempt == self.max_download_attempts:
                    break
                await asyncio.sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        raise last_error

    async def _download_attempt(
        self,
        destination: Path,
        *,
        temp_destination: Path,
        show_progress: bool,
    ) -> tuple[int, str]:
        """Perform one ranged request and retain partial bytes after interruption."""
        downloaded_bytes = (
            temp_destination.stat().st_size if temp_destination.exists() else 0
        )
        headers = dict(self.header)
        if downloaded_bytes:
            headers["Range"] = f"bytes={downloaded_bytes}-"

        async with self.client.stream("GET", self.url, headers=headers) as response:
            if response.status_code == 416 and downloaded_bytes:
                total = response.headers.get("Content-Range", "").partition("*/")[2]
                if total.isdigit() and downloaded_bytes == int(total):
                    digest = self._sha256(temp_destination)
                    temp_destination.replace(destination)
                    return downloaded_bytes, digest
            response.raise_for_status()

            resumed = response.status_code == 206 and downloaded_bytes > 0
            if resumed:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {downloaded_bytes}-"):
                    raise httpx.ProtocolError(
                        f"Unexpected Content-Range while resuming: {content_range!r}"
                    )
            else:
                downloaded_bytes = 0

            digest = hashlib.sha256()
            if resumed:
                with temp_destination.open("rb") as existing:
                    while chunk := existing.read(1024 * 1024):
                        digest.update(chunk)

            remaining = _content_length(response)
            total = downloaded_bytes + remaining if remaining is not None else None
            mode = "ab" if resumed else "wb"
            with (
                temp_destination.open(mode) as output,
                tqdm(
                    total=total,
                    initial=downloaded_bytes,
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
        return downloaded_bytes, digest.hexdigest()

    @staticmethod
    def _sha256(path: Path) -> str:
        """Calculate the digest of a completed partial file."""
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

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
