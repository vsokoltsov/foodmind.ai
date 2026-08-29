import asyncio
import hashlib
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.clients.openfoodfacts.client import OpenFoodFactsClient

OPEN_FOOD_FACTS_URL = (
    "https://static.openfoodfacts.org/data/"
    "openfoodfacts-products.jsonl.gz"
)


@pytest.fixture
def http_client() -> Iterator[httpx.AsyncClient]:
    """Provide an async HTTP client intercepted by pytest-httpx."""
    client = httpx.AsyncClient()
    yield client
    asyncio.run(client.aclose())


@pytest.fixture
def open_food_facts_client(
    http_client: httpx.AsyncClient,
) -> OpenFoodFactsClient:
    """Provide an Open Food Facts client using the test HTTP transport."""
    return OpenFoodFactsClient(client=http_client)


def test_downloads_export_and_displays_byte_progress(
    httpx_mock: HTTPXMock,
    open_food_facts_client: OpenFoodFactsClient,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = b"compressed-open-food-facts-export"
    httpx_mock.add_response(
        method="GET",
        url=OPEN_FOOD_FACTS_URL,
        headers={"Content-Length": str(len(content))},
        content=content,
    )
    destination = tmp_path / "openfoodfacts-products.jsonl.gz"

    artifact = asyncio.run(
        open_food_facts_client.get_facts(
            str(destination),
            show_progress=True,
        )
    )

    assert destination.read_bytes() == content
    assert artifact.path == destination
    assert artifact.size_bytes == len(content)
    assert artifact.sha256 == hashlib.sha256(content).hexdigest()
    assert not destination.with_suffix(destination.suffix + ".tmp").exists()

    progress_output = capsys.readouterr().err
    assert destination.name in progress_output
    assert "100%" in progress_output

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Accept"] == "*/*"


def test_download_is_quiet_by_default(
    httpx_mock: HTTPXMock,
    open_food_facts_client: OpenFoodFactsClient,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=OPEN_FOOD_FACTS_URL,
        content=b"export",
    )

    asyncio.run(
        open_food_facts_client.get_facts(
            str(tmp_path / "openfoodfacts-products.jsonl.gz")
        )
    )

    assert capsys.readouterr().err == ""


def test_resumes_an_existing_partial_download(
    httpx_mock: HTTPXMock,
    http_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "openfoodfacts-products.jsonl.gz"
    partial = destination.with_suffix(destination.suffix + ".tmp")
    partial.write_bytes(b"first-")
    httpx_mock.add_response(
        method="GET",
        url=OPEN_FOOD_FACTS_URL,
        status_code=206,
        headers={
            "Content-Length": "6",
            "Content-Range": "bytes 6-11/12",
        },
        content=b"second",
    )

    artifact = asyncio.run(
        OpenFoodFactsClient(client=http_client).get_facts(str(destination))
    )

    assert destination.read_bytes() == b"first-second"
    assert artifact.size_bytes == 12
    assert artifact.sha256 == hashlib.sha256(b"first-second").hexdigest()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Range"] == "bytes=6-"


def test_retries_a_transient_server_error(
    httpx_mock: HTTPXMock,
    http_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=OPEN_FOOD_FACTS_URL,
        status_code=503,
    )
    httpx_mock.add_response(
        method="GET",
        url=OPEN_FOOD_FACTS_URL,
        content=b"export",
    )
    destination = tmp_path / "openfoodfacts-products.jsonl.gz"

    artifact = asyncio.run(
        OpenFoodFactsClient(
            client=http_client,
            retry_delay_seconds=0,
        ).get_facts(str(destination))
    )

    assert destination.read_bytes() == b"export"
    assert artifact.size_bytes == 6
    assert len(httpx_mock.get_requests()) == 2


def test_does_not_create_partial_file_when_request_is_rejected(
    httpx_mock: HTTPXMock,
    open_food_facts_client: OpenFoodFactsClient,
    tmp_path: Path,
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=OPEN_FOOD_FACTS_URL,
        status_code=503,
    )
    destination = tmp_path / "openfoodfacts-products.jsonl.gz"

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            OpenFoodFactsClient(
                client=open_food_facts_client.client,
                max_download_attempts=1,
            ).get_facts(str(destination))
        )

    assert not destination.exists()
    assert not destination.with_suffix(destination.suffix + ".tmp").exists()
