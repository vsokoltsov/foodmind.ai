from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DownloadArtifact(BaseModel):
    """Metadata describing a downloaded Open Food Facts export."""

    model_config = ConfigDict(frozen=True)

    source_url: str
    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OpenFoodFactsProduct(BaseModel):
    """MVP fields read from one Open Food Facts JSON Lines record.

    Open Food Facts records contain many generated and evolving fields. Unknown
    fields are intentionally ignored so the streaming reader remains compatible
    with newer exports while validating the fields used by FoodMind.
    """

    model_config = ConfigDict(extra="ignore")

    code: str
    product_name: str | None = None
    generic_name: str | None = None
    brands: str | None = None
    brands_tags: list[str] = Field(default_factory=list)
    categories: str | None = None
    categories_tags: list[str] = Field(default_factory=list)
    countries: str | None = None
    countries_tags: list[str] = Field(default_factory=list)
    ingredients_text: str | None = None
    ingredients_tags: list[str] = Field(default_factory=list)
    allergens: str | None = None
    allergens_tags: list[str] = Field(default_factory=list)
    traces: str | None = None
    traces_tags: list[str] = Field(default_factory=list)
    labels_tags: list[str] = Field(default_factory=list)
    quantity: str | None = None
    serving_size: str | None = None
    nutrition_grades: str | None = None
    nova_group: int | None = None
    nutriments: dict[str, int | float | str | None] = Field(default_factory=dict)
    image_url: str | None = None
    image_front_url: str | None = None
    last_modified_t: int | None = None
