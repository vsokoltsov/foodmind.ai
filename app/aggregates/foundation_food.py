"""Canonical USDA Foundation Food business object."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.aggregates.nutrition import Nutrition


class FoundationFood(BaseModel):
    """Canonical USDA Foundation Food business object."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: Literal["usda_fdc"] = "usda_fdc"
    entity_type: Literal["foundation_food"] = "foundation_food"
    label: str
    description: str | None = None
    fdc_id: int
    category: str
    scientific_name: str | None = None
    publication_date: str
    nutrients: list[Nutrition] = Field(default_factory=list)
