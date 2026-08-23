import asyncio
import hashlib
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.clients.usda_fdc.client import USDAFoundationClient, _extract_links

DOWNLOADS_URL = "https://fdc.nal.usda.gov/download-datasets/"
FOUNDATION_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/"
    "FoodData_Central_foundation_food_json_2026-04-30.zip"
)
BRANDED_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/"
    "FoodData_Central_branded_food_json_2026-04-30.zip"
)


@pytest.fixture
def http_client() -> Iterator[httpx.AsyncClient]:
    """Provide an async HTTP client and close it after each test."""
    client = httpx.AsyncClient(follow_redirects=True)
    yield client
    asyncio.run(client.aclose())


@pytest.fixture
def usda_client(http_client: httpx.AsyncClient) -> USDAFoundationClient:
    """Provide a USDA client whose HTTP calls are intercepted by pytest-httpx."""
    return USDAFoundationClient(client=http_client)


@pytest.fixture
def downloads_page() -> str:
    """Return a representative USDA downloads page containing both exports."""
    return f"""
    <html>
      <body>
        <a href="{FOUNDATION_URL}">
          <strong>Foundation Foods</strong> April 2026 (JSON)
        </a>
        <a href="/fdc-datasets/FoodData_Central_branded_food_json_2026-04-30.zip">
          Branded Foods April 2026 (JSON)
        </a>
      </body>
    </html>
    """


def test_extract_links_resolves_urls_and_normalizes_html_text() -> None:
    html = '<a class="download" href="files/data.json.zip"> JSON <b>file</b> </a>'

    assert _extract_links(html, DOWNLOADS_URL) == [
        ("https://fdc.nal.usda.gov/download-datasets/files/data.json.zip", "JSON file")
    ]


@pytest.mark.parametrize(
    ("method_name", "download_url", "archive_content"),
    [
        ("get_foundations", FOUNDATION_URL, b"foundation-zip-content"),
        ("get_branded", BRANDED_URL, b"branded-zip-content"),
    ],
)
def test_downloads_complete_usda_archive_through_http_server(
    httpx_mock: HTTPXMock,
    usda_client: USDAFoundationClient,
    downloads_page: str,
    tmp_path: Path,
    method_name: str,
    download_url: str,
    archive_content: bytes,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=DOWNLOADS_URL,
        html=downloads_page,
    )
    httpx_mock.add_response(
        method="GET",
        url=download_url,
        content=archive_content,
    )
    destination = tmp_path / f"{method_name}.json.zip"

    artifact = asyncio.run(getattr(usda_client, method_name)(str(destination)))

    assert destination.read_bytes() == archive_content
    assert not destination.with_suffix(destination.suffix + ".tmp").exists()
    assert artifact.source_url == download_url
    assert artifact.path == destination
    assert artifact.size_bytes == len(archive_content)
    assert artifact.sha256 == hashlib.sha256(archive_content).hexdigest()

    requests = httpx_mock.get_requests()
    assert [str(request.url) for request in requests] == [
        DOWNLOADS_URL,
        download_url,
    ]
    assert requests[1].headers["Accept"] == "*/*"
    assert requests[1].headers["Accept-Language"] == "en-US,en;q=0.9"


def test_discovers_download_by_href_when_link_text_does_not_match(
    httpx_mock: HTTPXMock,
    usda_client: USDAFoundationClient,
    tmp_path: Path,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=DOWNLOADS_URL,
        html=f'<a href="{FOUNDATION_URL}">Download archive</a>',
    )
    httpx_mock.add_response(
        method="GET",
        url=FOUNDATION_URL,
        content=b"archive",
    )
    destination = tmp_path / "foundation.json.zip"

    artifact = asyncio.run(usda_client.get_foundations(str(destination)))

    assert destination.read_bytes() == b"archive"
    assert artifact.path == destination


def test_raises_when_download_link_cannot_be_discovered(
    httpx_mock: HTTPXMock,
    usda_client: USDAFoundationClient,
    tmp_path: Path,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=DOWNLOADS_URL,
        html='<a href="unrelated.csv">Unrelated CSV</a>',
    )

    with pytest.raises(RuntimeError, match="Could not discover download link"):
        asyncio.run(
            usda_client.get_foundations(str(tmp_path / "foundation.json.zip"))
        )

    assert len(httpx_mock.get_requests()) == 1


def test_propagates_download_http_error_without_replacing_destination(
    httpx_mock: HTTPXMock,
    usda_client: USDAFoundationClient,
    downloads_page: str,
    tmp_path: Path,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=DOWNLOADS_URL,
        html=downloads_page,
    )
    httpx_mock.add_response(
        method="GET",
        url=FOUNDATION_URL,
        status_code=503,
        text="temporarily unavailable",
    )
    destination = tmp_path / "foundation.json.zip"

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(usda_client.get_foundations(str(destination)))

    assert not destination.exists()
    assert not destination.with_suffix(destination.suffix + ".tmp").exists()
