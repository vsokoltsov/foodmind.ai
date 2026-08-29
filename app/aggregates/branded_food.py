"""Canonical USDA Branded Food business object."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.aggregates.nutrition import Nutrition


class BrandedFood(BaseModel):
    """Canonical USDA Branded Food business object."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: Literal["usda_fdc"] = "usda_fdc"
    entity_type: Literal["branded_food"] = "branded_food"
    label: str
    description: str | None = None
    fdc_id: int
    category: str
    brand_owner: str
    brand_name: str | None = None
    gtin_upc: str
    ingredients: str
    market_country: str
    publication_date: str
    serving_size: float
    serving_size_unit: str
    nutrients: list[Nutrition] = Field(default_factory=list)
