"""Tests for the repository-backed food-search agent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.aggregates import FoodEntity, OpenFoodFactsProduct
from app.agents.food_search import (
    FoodSearchAgent,
    FoodSearchDependencies,
    FoodSearchRequest,
    FoodSource,
)


def _dependencies() -> FoodSearchDependencies:
    """Create repository doubles for one agent test."""
    return FoodSearchDependencies(
        wikidata=SimpleNamespace(
            search=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        ),
        usda=SimpleNamespace(
            search_foundations=AsyncMock(return_value=[]),
            search_branded=AsyncMock(return_value=[]),
        ),
        openfoodfacts=SimpleNamespace(search=AsyncMock(return_value=[])),
    )


def _context(deps: FoodSearchDependencies) -> SimpleNamespace:
    """Build the minimal runtime context required by tool methods."""
    return SimpleNamespace(deps=deps)


def test_request_validates_source_and_limit() -> None:
    """A search request accepts enum values and rejects invalid limits."""
    request = FoodSearchRequest(source=FoodSource.OPENFOODFACTS, limit=5)

    assert request.source is FoodSource.OPENFOODFACTS

    with pytest.raises(ValidationError):
        FoodSearchRequest(limit=0)


def test_result_converts_wikidata_entity() -> None:
    """Wikidata domain objects receive source and entity type metadata."""
    food = FoodEntity(id="Q123", label="Apple")

    result = FoodSearchAgent._result(food)

    assert result.model_dump() == {
        "id": "Q123",
        "label": "Apple",
        "source": "wikidata",
        "entity_type": "food_concept",
        "description": None,
    }


def test_search_foods_routes_openfoodfacts_filters() -> None:
    """The Open Food Facts source receives the relevant typed query."""
    deps = _dependencies()
    product = OpenFoodFactsProduct(id="openfoodfacts:123", code="123", label="Apple")
    deps.openfoodfacts.search.return_value = [product]
    agent = FoodSearchAgent()

    results = asyncio.run(
        agent.search_foods(
            _context(deps),
            FoodSearchRequest(
                source=FoodSource.OPENFOODFACTS,
                text="123",
                country="Germany",
                brand="Example",
            ),
        )
    )

    query = deps.openfoodfacts.search.await_args.args[0]
    assert query.text == "123"
    assert query.barcode == "123"
    assert query.country == "Germany"
    assert query.brand == "Example"
    assert results[0].id == "openfoodfacts:123"


def test_search_foods_queries_all_sources_concurrently() -> None:
    """An unspecified source queries every repository and limits combined results."""
    deps = _dependencies()
    deps.wikidata.search.return_value = [FoodEntity(id="Q1", label="Apple")]
    deps.openfoodfacts.search.return_value = [
        OpenFoodFactsProduct(id="openfoodfacts:1", code="1", label="Apple")
    ]
    agent = FoodSearchAgent()

    results = asyncio.run(
        agent.search_foods(
            _context(deps), FoodSearchRequest(text="apple", limit=1)
        )
    )

    assert len(results) == 1
    deps.wikidata.search.assert_awaited_once()
    deps.usda.search_foundations.assert_awaited_once()
    deps.usda.search_branded.assert_awaited_once()
    deps.openfoodfacts.search.assert_awaited_once()


def test_lookup_wikidata_entity_returns_none_when_missing() -> None:
    """The Wikidata lookup tool returns None for an unknown identifier."""
    deps = _dependencies()
    agent = FoodSearchAgent()

    result = asyncio.run(
        agent.lookup_wikidata_entity(_context(deps), "Q404")
    )

    assert result is None
    deps.wikidata.get_by_id.assert_awaited_once_with("Q404")
