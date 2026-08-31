"""Validated query objects used by Elasticsearch repositories."""

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Common pagination and free-text search options."""

    text: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class WikidataFoodQuery(SearchQuery):
    """Search criteria for Wikidata food concepts."""

    cuisine_id: str | None = None
    country_id: str | None = None


class USDAFoodQuery(SearchQuery):
    """Search criteria shared by USDA Foundation and Branded Foods."""

    category: str | None = None


class BrandedFoodQuery(USDAFoodQuery):
    """Search criteria for USDA Branded Foods."""

    brand: str | None = None


class OpenFoodFactsQuery(SearchQuery):
    """Search criteria for Open Food Facts products."""

    barcode: str | None = None
    brand: str | None = None
    country: str | None = None
