"""Canonical nutrition business object."""

from pydantic import BaseModel, ConfigDict


class Nutrition(BaseModel):
    """A nutrient measurement normalized to the application's vocabulary."""

    model_config = ConfigDict(frozen=True)

    id: int
    number: str
    name: str
    unit: str
    amount: float | None
