import asyncio
from collections.abc import Iterator
from urllib.parse import parse_qs

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.clients.models import USER_AGENT
from app.clients.wikidata_food_entities.client import WikidataFoodEntitiesClient
from app.clients.wikidata_food_entities.models import (
    WikiDataAliasResponse,
    WikiDataResponse,
    WikidataMediaArticlesResponse,
    WikidataOriginalCuisineResponse,
    WikidataTaxonomyResponse,
)

WIKIDATA_URL = "https://query.wikidata.org/sparql"


@pytest.fixture
def http_client() -> Iterator[httpx.AsyncClient]:
    """Provide an async HTTP client and close it after each test."""
    client = httpx.AsyncClient()
    yield client
    asyncio.run(client.aclose())


@pytest.fixture
def wikidata_client(http_client: httpx.AsyncClient) -> WikidataFoodEntitiesClient:
    """Provide a Wikidata client configured for fast retry tests."""
    return WikidataFoodEntitiesClient(
        client=http_client,
        batch_size=2,
        retry_base_delay_seconds=0.001,
    )


@pytest.fixture
def item_value() -> dict[str, str]:
    """Return a representative Wikidata URI binding value."""
    return {
        "type": "uri",
        "value": "http://www.wikidata.org/entity/Q123",
    }


@pytest.fixture
def literal_value() -> dict[str, str]:
    """Return a representative English Wikidata literal binding value."""
    return {
        "type": "literal",
        "value": "Test food",
        "xml:lang": "en",
    }


def add_sparql_response(
    httpx_mock: HTTPXMock,
    bindings: list[dict[str, object]],
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> None:
    """Register a mocked Wikidata SPARQL response."""
    httpx_mock.add_response(
        method="POST",
        url=WIKIDATA_URL,
        status_code=status_code,
        headers=headers,
        json={"head": {"vars": []}, "results": {"bindings": bindings}},
    )


def request_query(request: httpx.Request) -> str:
    """Extract the SPARQL query from an HTTP request body."""
    return parse_qs(request.content.decode())["query"][0]


def test_get_entities_returns_full_validated_response(
    httpx_mock: HTTPXMock,
    wikidata_client: WikidataFoodEntitiesClient,
    item_value: dict[str, str],
    literal_value: dict[str, str],
) -> None:
    binding = {
        "item": item_value,
        "itemLabel": literal_value,
        "itemDescription": {
            "type": "literal",
            "value": "A test food entity",
            "xml:lang": "en",
        },
    }
    add_sparql_response(httpx_mock, [binding])

    response = asyncio.run(wikidata_client.get_entities())

    assert isinstance(response, WikiDataResponse)
    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "results": {"bindings": [binding]},
    }
    assert response.results.qids == ["wd:Q123"]

    request = httpx_mock.get_request()
    assert request is not None
    assert "wdt:P279* wd:Q2095" in request_query(request)
    assert request.headers["Accept"] == "application/sparql-results+json"
    assert request.headers["User-Agent"] == USER_AGENT


def test_get_aliases_batches_requests_and_returns_full_response(
    httpx_mock: HTTPXMock,
    wikidata_client: WikidataFoodEntitiesClient,
    item_value: dict[str, str],
) -> None:
    first_binding = {
        "item": item_value,
        "alias": {"type": "literal", "value": "First", "xml:lang": "en"},
    }
    second_binding = {
        "item": {
            "type": "uri",
            "value": "http://www.wikidata.org/entity/Q456",
        },
        "alias": {"type": "literal", "value": "Second", "xml:lang": "en"},
    }
    add_sparql_response(httpx_mock, [first_binding])
    add_sparql_response(httpx_mock, [second_binding])

    response = asyncio.run(
        wikidata_client.get_aliases(["wd:Q123", "wd:Q456", "wd:Q789"])
    )

    assert isinstance(response, WikiDataAliasResponse)
    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "results": {"bindings": [first_binding, second_binding]},
    }
    queries = [request_query(request) for request in httpx_mock.get_requests()]
    assert "wd:Q123" in queries[0]
    assert "wd:Q456" in queries[0]
    assert "wd:Q789" in queries[1]
    assert all("$items" not in query for query in queries)


def test_get_taxonomy_returns_full_validated_response(
    httpx_mock: HTTPXMock,
    wikidata_client: WikidataFoodEntitiesClient,
    item_value: dict[str, str],
    literal_value: dict[str, str],
) -> None:
    binding = {
        "item": item_value,
        "instance": {
            "type": "uri",
            "value": "http://www.wikidata.org/entity/Q2095",
        },
        "instanceLabel": literal_value,
        "subclass": {
            "type": "uri",
            "value": "http://www.wikidata.org/entity/Q25403900",
        },
        "subclassLabel": {
            "type": "literal",
            "value": "Food ingredient",
            "xml:lang": "en",
        },
    }
    add_sparql_response(httpx_mock, [binding])

    response = asyncio.run(wikidata_client.get_taxonomy(["wd:Q123"]))

    assert isinstance(response, WikidataTaxonomyResponse)
    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "results": {"bindings": [binding]},
    }
    request = httpx_mock.get_request()
    assert request is not None
    assert "wd:Q123" in request_query(request)
    assert "wdt:P31" in request_query(request)


def test_get_original_cousine_returns_full_validated_response(
    httpx_mock: HTTPXMock,
    wikidata_client: WikidataFoodEntitiesClient,
    item_value: dict[str, str],
) -> None:
    binding = {
        "item": item_value,
        "country": {
            "type": "uri",
            "value": "http://www.wikidata.org/entity/Q38",
        },
        "countryLabel": {
            "type": "literal",
            "value": "Italy",
            "xml:lang": "en",
        },
        "cuisine": {
            "type": "uri",
            "value": "http://www.wikidata.org/entity/Q192786",
        },
        "cuisineLabel": {
            "type": "literal",
            "value": "Italian cuisine",
            "xml:lang": "en",
        },
    }
    add_sparql_response(httpx_mock, [binding])

    response = asyncio.run(wikidata_client.get_original_cousine(["wd:Q123"]))

    assert isinstance(response, WikidataOriginalCuisineResponse)
    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "results": {"bindings": [binding]},
    }
    request = httpx_mock.get_request()
    assert request is not None
    assert "wdt:P495" in request_query(request)
    assert "wdt:P2012" in request_query(request)


def test_get_media_articles_returns_full_validated_response(
    httpx_mock: HTTPXMock,
    wikidata_client: WikidataFoodEntitiesClient,
    item_value: dict[str, str],
) -> None:
    binding = {
        "item": item_value,
        "image": {
            "type": "uri",
            "value": "http://commons.wikimedia.org/wiki/Special:FilePath/Food.jpg",
        },
        "article": {
            "type": "uri",
            "value": "https://en.wikipedia.org/wiki/Test_food",
        },
    }
    add_sparql_response(httpx_mock, [binding])

    response = asyncio.run(wikidata_client.get_media_articles(["wd:Q123"]))

    assert isinstance(response, WikidataMediaArticlesResponse)
    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "results": {"bindings": [binding]},
    }
    request = httpx_mock.get_request()
    assert request is not None
    assert "wdt:P18" in request_query(request)
    assert "https://en.wikipedia.org/" in request_query(request)


def test_retries_retryable_http_response_then_returns_response(
    httpx_mock: HTTPXMock,
    wikidata_client: WikidataFoodEntitiesClient,
) -> None:
    add_sparql_response(
        httpx_mock,
        [],
        status_code=503,
        headers={"Retry-After": "0"},
    )
    add_sparql_response(httpx_mock, [])

    response = asyncio.run(wikidata_client.get_entities())

    assert response.model_dump() == {"results": {"bindings": []}}
    assert len(httpx_mock.get_requests()) == 2


def test_retries_invalid_json_then_raises_runtime_error(
    httpx_mock: HTTPXMock,
    http_client: httpx.AsyncClient,
) -> None:
    client = WikidataFoodEntitiesClient(
        client=http_client,
        max_retries=1,
        retry_base_delay_seconds=0.001,
    )
    httpx_mock.add_response(method="POST", url=WIKIDATA_URL, text="not-json")
    httpx_mock.add_response(method="POST", url=WIKIDATA_URL, text="still-not-json")

    with pytest.raises(RuntimeError, match="Wikidata returned invalid JSON"):
        asyncio.run(client.get_entities())

    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize(
    ("argument", "value", "message"),
    [
        ("batch_size", 0, "batch_size must be at least 1"),
        ("concurrency", 0, "concurrency must be at least 1"),
        ("max_retries", -1, "max_retries must be at least 0"),
        (
            "retry_base_delay_seconds",
            0,
            "retry_base_delay_seconds must be greater than 0",
        ),
    ],
)
def test_rejects_invalid_configuration(
    http_client: httpx.AsyncClient,
    argument: str,
    value: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        WikidataFoodEntitiesClient(client=http_client, **{argument: value})
