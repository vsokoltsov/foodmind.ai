"""HTTP client for downloading USDA FoodData Central archives."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.clients.usda_fdc.models import DownloadArtifact


def _sha256(path: Path) -> str:
    """Calculate the SHA-256 checksum of a downloaded file."""
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for block in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    anchor_pattern = re.compile(
        r'<a\s+[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>'
        r"(?P<text>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    links: list[tuple[str, str]] = []
    for match in anchor_pattern.finditer(html):
        href = urljoin(base_url, match.group("href"))
        text = re.sub(r"<[^>]+>", " ", match.group("text"))
        text = " ".join(text.split())
        links.append((href, text))
    return links

@dataclass
class USDAFoundationClient:
    client: httpx.AsyncClient
    url: str = "https://fdc.nal.usda.gov/download-datasets/"

    @property
    def header(self) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9"
        }

    async def _discover_link(
        self,
        href_contains: tuple[str, ...],
        link_text_contains: tuple[str, ...],
    ) -> str:
        response = await self.client.get(self.url)
        response.raise_for_status()

        links = _extract_links(response.text, base_url=self.url)
        for href, text in links:
            normalized_href = href.lower()
            normalized_text = text.lower()
            href_matches = all(
                term.lower() in normalized_href for term in href_contains
            )
            text_matches = all(
                term.lower() in normalized_text for term in link_text_contains
            )
            if href_matches and text_matches:
                return href

        for href, _text in links:
            normalized_href = href.lower()
            if all(term.lower() in normalized_href for term in href_contains):
                return href

        raise RuntimeError(f"Could not discover download link for {href_contains}")

    async def _download_file(self, url: str, destination: Path) -> None:
        temp_destination = destination.with_suffix(destination.suffix + ".tmp")
        try:
            async with self.client.stream("GET", url, headers=self.header) as response:
                response.raise_for_status()
                with temp_destination.open("wb") as output:
                    async for chunk in response.aiter_bytes():
                        output.write(chunk)
            temp_destination.replace(destination)
        except BaseException:
            temp_destination.unlink(missing_ok=True)
            raise

    async def _get_entity(
        self,
        destination_file: str,
        href_contains: tuple[str, ...],
        link_text_contains: tuple[str, ...]
    ) -> DownloadArtifact:
        dest_file = Path(destination_file)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        source_url = await self._discover_link(
            href_contains=href_contains,
            link_text_contains=link_text_contains,
        )
        await self._download_file(
            url=source_url,
            destination=dest_file
        )
        return DownloadArtifact(
            source_url=source_url,
            path=dest_file,
            size_bytes=dest_file.stat().st_size,
            sha256=_sha256(dest_file),
        )


    async def get_foundations(self, destination_file: str) -> DownloadArtifact:
        return await self._get_entity(
            destination_file=destination_file,
            href_contains=("foundation", "json"),
            link_text_contains=("Foundation Foods", "JSON"),
        )

    async def get_branded(self, destination_file: str) -> DownloadArtifact:
        return await self._get_entity(
            destination_file=destination_file,
            href_contains=("branded", "json"),
            link_text_contains=("Branded", "JSON"),
        )
