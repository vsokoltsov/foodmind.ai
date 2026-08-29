"""Canonical Open Food Facts product business object."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OpenFoodFactsProduct(BaseModel):
    """Canonical Open Food Facts product business object."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: Literal["openfoodfacts"] = "openfoodfacts"
    entity_type: Literal["product"] = "product"
    label: str
    description: str | None = None
    code: str
    brands: str | None = None
    brands_tags: list[str] = Field(default_factory=list)
    categories: str | None = None
    categories_tags: list[str] = Field(default_factory=list)
    countries: str | None = None
    countries_tags: list[str] = Field(default_factory=list)
    ingredients: str | None = None
    ingredients_tags: list[str] = Field(default_factory=list)
    allergens: str | None = None
    allergens_tags: list[str] = Field(default_factory=list)
    traces: str | None = None
    traces_tags: list[str] = Field(default_factory=list)
    labels_tags: list[str] = Field(default_factory=list)
    quantity: str | None = None
    serving_size: str | None = None
    nutrition_grade: str | None = None
    nova_group: int | None = None
    nutriments: dict[str, int | float | str | None] = Field(default_factory=dict)
    image_url: str | None = None
    image_front_url: str | None = None
    last_modified_at: int | None = None
